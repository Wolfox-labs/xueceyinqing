export const MCP_TOOLS = [
  {
    name: 'ask_teacher',
    description: '向 AI 教师提问，获取个性化学习指导',
    inputSchema: {
      type: 'object',
      properties: {
        question: { type: 'string', description: '用户的问题' },
        context: { type: 'string', description: '对话上下文' },
      },
      required: ['question'],
    },
  },
  {
    name: 'generate_resource',
    description: '生成学习资源（文档/思维导图/练习题/阅读材料/视频脚本/代码示例）',
    inputSchema: {
      type: 'object',
      properties: {
        type: {
          type: 'string',
          enum: ['document', 'mindmap', 'exercise', 'reading', 'video_script', 'code_example'],
          description: '资源类型',
        },
        topic: { type: 'string', description: '资源主题' },
      },
      required: ['type', 'topic'],
    },
  },
  {
    name: 'get_profile',
    description: '获取用户画像和学习进度数据',
    inputSchema: {
      type: 'object',
      properties: {
        user_id: { type: 'string', description: '用户ID' },
      },
      required: ['user_id'],
    },
  },
] as const

export type MCPToolName = (typeof MCP_TOOLS)[number]['name']