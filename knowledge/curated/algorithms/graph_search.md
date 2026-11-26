---
title: "图搜索：BFS 与 DFS"
module: "算法设计"
knowledge_point: "图搜索"
difficulty: "综合"
prerequisites: ["列表与迭代", "算法基础"]
tags: ["algorithm", "graph", "bfs", "dfs"]
source: "算法设计与分析讲义"
source_url: "https://oi-wiki.org/graph/"
---

# 图搜索：BFS 与 DFS

## 图的表示
邻接表适合稀疏图：`graph[u]` 保存与节点 `u` 相邻的所有节点。

## 广度优先搜索 BFS
BFS 按层扩展，常使用队列，适合无权图最短路径和层序遍历。每个节点入队一次，时间复杂度 `O(V+E)`。

## 深度优先搜索 DFS
DFS 沿一条路径深入，使用递归或栈，适合连通性、环检测、拓扑排序和回溯。

## Python 示例
```python
from collections import deque

def bfs(graph, start):
    queue = deque([start])
    seen = {start}
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for next_node in graph[node]:
            if next_node not in seen:
                seen.add(next_node)
                queue.append(next_node)
    return order
```

## 常见错误
- 入队时才标记会重复访问，应该在入队时标记。
- 有向图和无向图的边界处理不同。
- 递归 DFS 过深时应改用显式栈。
