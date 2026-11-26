"""图片/扫描件接入资料链路的回归测试。

本文件**不联网**：多模态调用一律打桩，只验证三件事——
  1. 选对了抽取路径（图片走识别、有文字层的 PDF 不浪费识别调用）；
  2. 发给多模态接口的报文结构正确（这是最容易写错的一环）；
  3. 失败语义正确（服务侧故障 ≠ 文件本身有问题）。

真实识别效果由 runtime 下的端到端探针用真图片单独验证，不在这里假装通过。
"""
import gc
import re
import shutil
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

from core import material_service as ms
from core import vision_ocr


def _png_bytes(size=(64, 64)) -> bytes:
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", size, (240, 240, 240)).save(buffer, format="PNG")
    return buffer.getvalue()


def _pdf_bytes(with_text: bool, text: str = "hello material") -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    if with_text:
        page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


class MaterialImageExtractionTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="matimg_"))
        # 默认路径指向真实 runtime/app.db 与 runtime/data/materials，
        # 测试必须改到临时目录，避免污染真实库。
        self._db_patch = mock.patch.object(ms, "_DEFAULT_DB_PATH", self.root / "materials.db")
        self._root_patch = mock.patch.object(ms, "_MATERIALS_ROOT", self.root / "store")
        self._db_patch.start()
        self._root_patch.start()
        self.service = ms.MaterialService()

    def tearDown(self):
        self._root_patch.stop()
        self._db_patch.stop()
        # sqlite3 的 `with conn:` 只提交事务、不关闭连接，句柄要等对象被回收才释放；
        # Windows 上这会短暂锁住 .db 文件，所以先回收再删除，删不掉也不让测试误报失败。
        del self.service
        gc.collect()
        shutil.rmtree(self.root, ignore_errors=True)

    # ── 格式白名单 ──────────────────────────────────────
    def test_image_suffixes_are_accepted(self):
        for suffix in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"):
            self.assertIn(suffix, ms.ALLOWED_SUFFIXES, f"{suffix} 应被接受")

    def test_document_suffixes_still_accepted(self):
        for suffix in (".docx", ".pdf", ".md", ".markdown", ".txt"):
            self.assertIn(suffix, ms.ALLOWED_SUFFIXES, f"{suffix} 不应被移除")

    def test_frontend_accept_matches_backend_whitelist(self):
        """前端白名单必须与后端完全一致。

        前端会用 ACCEPT 做一次本地格式校验，两边不一致就会出现
        "后端明明支持、界面却先拦下"的假拒绝（.gif 曾经就是这样漏掉的）。
        """
        tsx = (
            Path(__file__).resolve().parent.parent
            / "frontend" / "src" / "components" / "materials" / "MaterialsPanel.tsx"
        ).read_text(encoding="utf-8")
        match = re.search(r"const ACCEPT = '([^']+)'", tsx)
        self.assertIsNotNone(match, "未能在 MaterialsPanel.tsx 中找到 ACCEPT 常量")
        frontend = {item.strip() for item in match.group(1).split(",") if item.strip()}
        backend = set(ms.ALLOWED_SUFFIXES)
        self.assertEqual(
            frontend, backend,
            f"前端多出 {sorted(frontend - backend)}，后端多出 {sorted(backend - frontend)}",
        )

    # ── 路径选择 ────────────────────────────────────────
    def test_image_goes_through_vision(self):
        path = self.root / "q.png"
        path.write_bytes(_png_bytes())
        with mock.patch.object(ms, "extract_text_from_image_bytes", return_value="识别出的题目") as spy:
            self.assertEqual(self.service._extract_text(path, ".png"), "识别出的题目")
            spy.assert_called_once()

    def test_pdf_with_text_layer_does_not_call_vision(self):
        path = self.root / "typed.pdf"
        path.write_bytes(_pdf_bytes(with_text=True, text="typed pdf content"))
        with mock.patch.object(ms, "extract_text_from_pdf_via_vision") as spy:
            result = self.service._extract_text(path, ".pdf")
        spy.assert_not_called()
        self.assertIn("typed pdf content", result)

    def test_scanned_pdf_falls_back_to_vision(self):
        path = self.root / "scan.pdf"
        path.write_bytes(_pdf_bytes(with_text=False))
        with mock.patch.object(ms, "extract_text_from_pdf_via_vision", return_value="扫描页文字") as spy:
            self.assertEqual(self.service._extract_text(path, ".pdf"), "扫描页文字")
            spy.assert_called_once()

    # ── 入库 ────────────────────────────────────────────
    def test_add_material_stores_recognized_image_text(self):
        with mock.patch.object(ms, "extract_text_from_image_bytes", return_value="图里的文字"):
            item = self.service.add_material("u1", "题目截图.png", _png_bytes())
        self.assertEqual(item["file_type"], "png")
        stored = self.service.get_material("u1", item["id"])
        self.assertEqual(stored["extracted_text"], "图里的文字")

    def test_empty_recognition_is_rejected_and_file_cleaned(self):
        with mock.patch.object(ms, "extract_text_from_image_bytes", return_value="   "):
            with self.assertRaises(ValueError) as ctx:
                self.service.add_material("u1", "空白图.png", _png_bytes())
        self.assertIn("解析到文字", str(ctx.exception))
        leftovers = list((self.root / "store").rglob("*.png"))
        self.assertEqual(leftovers, [], "解析失败时应删除已落盘的文件")

    def test_unsupported_suffix_rejected(self):
        with self.assertRaises(ValueError):
            self.service.add_material("u1", "archive.zip", b"PK\x03\x04")

    # ── 失败的语义分类 ──────────────────────────────────
    def test_service_error_is_not_a_value_error(self):
        # 路由依赖这个区分：ValueError -> 400（文件问题），VisionServiceError -> 503（服务问题）。
        self.assertTrue(issubclass(vision_ocr.VisionServiceError, RuntimeError))
        self.assertFalse(issubclass(vision_ocr.VisionServiceError, ValueError))
        self.assertTrue(issubclass(vision_ocr.VisionNotConfigured, vision_ocr.VisionServiceError))

    def test_missing_config_raises_not_configured(self):
        with mock.patch.object(vision_ocr, "MODEL_LLM", {"base_url": "", "api_key": "", "model": "m"}), \
                mock.patch.object(vision_ocr, "VISION_MODEL", "m"):
            with self.assertRaises(vision_ocr.VisionNotConfigured):
                vision_ocr._recognize(b"x", "image/png", "p")

    def test_http_failure_raises_service_error(self):
        class FakeResponse:
            status_code = 500
            text = "boom"

        with mock.patch("httpx.post", return_value=FakeResponse()), \
                mock.patch.object(
                    vision_ocr, "MODEL_LLM",
                    {"base_url": "https://x/v1", "api_key": "k", "model": "m"},
                ), \
                mock.patch.object(vision_ocr, "VISION_MODEL", "vm"):
            with self.assertRaises(vision_ocr.VisionServiceError):
                vision_ocr._recognize(b"x", "image/png", "p")

    # ── 报文结构：最容易写错的一环 ──────────────────────
    def test_recognize_sends_openai_vision_payload(self):
        captured: dict = {}

        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": "转录结果"}}]}

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["json"] = kwargs.get("json")
            captured["timeout"] = kwargs.get("timeout")
            return FakeResponse()

        with mock.patch("httpx.post", fake_post), \
                mock.patch.object(
                    vision_ocr, "MODEL_LLM",
                    {"base_url": "https://api.example.com/v1", "api_key": "k", "model": "text-model"},
                ), \
                mock.patch.object(vision_ocr, "VISION_MODEL", "vision-model"):
            result = vision_ocr._recognize(b"\x89PNG-fake", "image/png", "请转录")

        self.assertEqual(result, "转录结果")
        self.assertEqual(captured["url"], "https://api.example.com/v1/chat/completions")
        body = captured["json"]
        self.assertEqual(body["model"], "vision-model", "应使用 vision_model 而不是主模型")
        parts = body["messages"][0]["content"]
        self.assertEqual(parts[0]["type"], "text")
        self.assertEqual(parts[1]["type"], "image_url")
        self.assertTrue(parts[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertIsNotNone(captured["timeout"], "必须设置超时，否则一次上传能把线程挂死")

    def test_content_parts_array_is_flattened(self):
        class FakeResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": [
                    {"type": "text", "text": "第一段"},
                    {"type": "text", "text": "第二段"},
                ]}}]}

        with mock.patch("httpx.post", return_value=FakeResponse()), \
                mock.patch.object(
                    vision_ocr, "MODEL_LLM",
                    {"base_url": "https://x/v1", "api_key": "k", "model": "m"},
                ), \
                mock.patch.object(vision_ocr, "VISION_MODEL", "vm"):
            self.assertEqual(vision_ocr._recognize(b"x", "image/png", "p"), "第一段第二段")

    # ── 图片预处理 ──────────────────────────────────────
    def test_oversized_image_is_downscaled(self):
        from PIL import Image

        prepared, mime = vision_ocr._prepare_image(_png_bytes(size=(3000, 120)))
        self.assertIn(mime, {"image/png", "image/jpeg"})
        with Image.open(BytesIO(prepared)) as image:
            self.assertLessEqual(max(image.size), vision_ocr._DOWNSCALE_MAX_SIDE)
            self.assertEqual(image.size[1] * 3000, image.size[0] * 120, "缩放应保持比例")

    def test_undecodable_bytes_pass_through(self):
        prepared, mime = vision_ocr._prepare_image(b"not an image at all")
        self.assertEqual(prepared, b"not an image at all")
        self.assertEqual(mime, "image/png")

    def test_vision_available_reflects_config(self):
        with mock.patch.object(
            vision_ocr, "MODEL_LLM",
            {"base_url": "https://x/v1", "api_key": "k", "model": "m"},
        ), mock.patch.object(vision_ocr, "VISION_MODEL", "vm"):
            self.assertTrue(vision_ocr.vision_available())
        with mock.patch.object(vision_ocr, "MODEL_LLM", {"base_url": "", "api_key": "", "model": "m"}), \
                mock.patch.object(vision_ocr, "VISION_MODEL", "m"):
            self.assertFalse(vision_ocr.vision_available())

    def test_scanned_pdf_respects_page_cap(self):
        events: list[int] = []

        class FakePixmap:
            @staticmethod
            def tobytes(fmt):
                return b"png"

        class FakePage:
            @staticmethod
            def get_pixmap(dpi):
                return FakePixmap()

        class FakeDoc:
            def __init__(self, count):
                self._pages = [FakePage() for _ in range(count)]

            def __len__(self):
                return len(self._pages)

            def __iter__(self):
                return iter(self._pages)

            def close(self):
                pass

        import fitz

        def fake_recognize(image_bytes, mime, prompt):
            events.append(1)
            return f"第{len(events)}页"

        with mock.patch.object(fitz, "open", lambda _p: FakeDoc(25)), mock.patch.object(
            vision_ocr, "_recognize", fake_recognize
        ):
            text = vision_ocr.extract_text_from_pdf_via_vision(Path("ignored.pdf"), max_pages=3)

        self.assertEqual(len(events), 3, "必须遵守页数上限，否则单次上传成本不可控")
        self.assertIn("第 1 页", text)
        self.assertIn("共 25 页", text, "应如实告知只识别了部分页")


if __name__ == "__main__":
    unittest.main()