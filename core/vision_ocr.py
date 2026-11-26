"""图片与扫描件的文字识别。

把图片（拍照的题目、截图、扫描版 PDF 页面）交给 OpenAI 兼容的多模态接口，
转录成纯文本，之后与 PDF／DOCX 抽取出的文本走**完全相同**的切块与检索链路。

为什么单独成模块：
  1. 这一步是"图 → 文字"的工具函数，不需要智能体编排，直连 httpx 即可，
     因此它可以在没有 crewai 的环境里被独立测试；
  2. 视觉模型可与主模型分开配置（VISION_MODEL），便于按成本/精度取舍。
"""
from __future__ import annotations

import base64
import logging
from io import BytesIO
from pathlib import Path

from config import MODEL_LLM, VISION_MODEL

logger = logging.getLogger(__name__)

# 常见位图与扫描格式。注意：这不代表"支持多模态"，只代表这些文件能被识别成文字。
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"})

_VISION_TIMEOUT_SECONDS = 90.0
# 扫描版 PDF 的页数上限：识别是逐页联网调用，不设上限会让一次上传的成本不可控。
SCANNED_PDF_MAX_PAGES = 10
_SCANNED_PDF_DPI = 150
_DOWNSCALE_MAX_SIDE = 2200
_MAX_TOKENS = 4000
_PNG_INLINE_LIMIT_BYTES = 3 * 1024 * 1024

TRANSCRIBE_PROMPT = (
    "请把这张图片中的内容完整、准确地转录为 Markdown 纯文本：\n"
    "1) 所有文字、题目编号、选项、代码原样保留，不要改写；\n"
    "2) 表格转成 Markdown 表格，公式用 LaTeX 写在 $...$ 中；\n"
    "3) 若图片是图表或流程图，用文字描述其结构与结论；\n"
    "4) 只依据图片内容作答，不要补充图中不存在的信息；无法辨认处写 [无法辨认]。"
)


class VisionServiceError(RuntimeError):
    """多模态接口不可用（网络、鉴权、上游报错）。属于服务侧问题，不是文件本身的问题。"""


class VisionNotConfigured(VisionServiceError):
    """没有配置可用的多模态接口。"""


def vision_model() -> str | None:
    """当前用于读图的模型：优先 VISION_MODEL，否则复用主模型。

    注意读的是 config.VISION_MODEL，而**不是** MODEL_LLM["vision_model"]：
    MODEL_LLM 是整份交给 crewai 的构造参数，多一个键就会让所有大模型调用报
    "unexpected keyword argument"。详见 config.py 里的警告。
    """
    return VISION_MODEL or MODEL_LLM.get("model")


def vision_available() -> bool:
    """是否具备调用多模态接口的最小配置。"""
    return bool(MODEL_LLM.get("base_url") and MODEL_LLM.get("api_key") and vision_model())


def _prepare_image(data: bytes) -> tuple[bytes, str]:
    """等比缩小超大图片并选择编码格式，避免把几十 MB 的原图直接塞进请求体。

    文本类截图优先用 PNG（无损，对识别更友好）；只有 PNG 仍然过大时才退回 JPEG。
    PIL 不可用时原样透传，不让图片处理成为识别的前置依赖。
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - PIL 在依赖里，这里只做兜底
        return data, "image/png"
    try:
        with Image.open(BytesIO(data)) as image:
            image = image.convert("RGB")
            longest = max(image.size)
            if longest > _DOWNSCALE_MAX_SIDE:
                scale = _DOWNSCALE_MAX_SIDE / float(longest)
                image = image.resize(
                    (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
                )
            buffer = BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            png = buffer.getvalue()
            if len(png) <= _PNG_INLINE_LIMIT_BYTES:
                return png, "image/png"
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=88, optimize=True)
            return buffer.getvalue(), "image/jpeg"
    except Exception as exc:  # noqa: BLE001 - 图片无法用 PIL 解析时仍尝试交给模型
        logger.debug("图片预处理失败，改为原样上传: %s", exc)
        return data, "image/png"


def _recognize(image_bytes: bytes, mime: str, prompt: str) -> str:
    """调用一次多模态接口，返回转录文本。"""
    base_url = str(MODEL_LLM.get("base_url") or "").rstrip("/")
    api_key = MODEL_LLM.get("api_key")
    model = vision_model()
    if not base_url or not api_key or not model:
        raise VisionNotConfigured("未配置多模态模型（LLM_BASE_URL / LLM_API_KEY / VISION_MODEL）")

    data_url = f"data:{mime};base64," + base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model,
        "max_tokens": _MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    }

    import httpx

    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=_VISION_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.warning("多模态接口请求失败: %s", exc)
        raise VisionServiceError("图片识别服务连接失败") from exc

    if response.status_code != 200:
        logger.warning("多模态接口返回 %s: %s", response.status_code, response.text[:500])
        raise VisionServiceError(f"图片识别服务返回异常（HTTP {response.status_code}）")

    try:
        message = (response.json().get("choices") or [{}])[0].get("message") or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("多模态接口响应无法解析: %s", exc)
        raise VisionServiceError("图片识别结果无法解析") from exc

    content = message.get("content")
    # 部分兼容实现会返回内容分片数组，拼起来即可。
    if isinstance(content, list):
        content = "".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    return str(content or "").strip()


def extract_text_from_image_bytes(data: bytes, prompt: str | None = None) -> str:
    """识别单张图片中的文字。"""
    if not data:
        raise ValueError("图片内容为空")
    prepared, mime = _prepare_image(data)
    return _recognize(prepared, mime, prompt or TRANSCRIBE_PROMPT)


def extract_text_from_pdf_via_vision(
    path: Path, max_pages: int = SCANNED_PDF_MAX_PAGES
) -> str:
    """扫描版 PDF 识别：逐页渲染成位图后交给多模态接口。

    仅在 PDF 抽不到文字层时调用，用于覆盖"扫描件/拍照转 PDF"这类原先会解析为空的文件。
    """
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - PyMuPDF 在依赖里
        raise VisionServiceError("缺少 PDF 渲染依赖（pymupdf），无法识别扫描版 PDF") from exc

    document = fitz.open(str(path))
    try:
        page_count = len(document)
        parts: list[str] = []
        for index, page in enumerate(document):
            if index >= max_pages:
                break
            pixmap = page.get_pixmap(dpi=_SCANNED_PDF_DPI)
            text = _recognize(pixmap.tobytes("png"), "image/png", TRANSCRIBE_PROMPT)
            if text:
                parts.append(f"[第 {index + 1} 页]\n{text}")
        if page_count > max_pages:
            parts.append(f"（该 PDF 共 {page_count} 页，本次只识别了前 {max_pages} 页）")
        return "\n\n".join(parts)
    finally:
        document.close()