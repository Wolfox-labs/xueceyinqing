---
title: "时间复杂度与空间复杂度"
module: "数据结构与算法"
knowledge_point: "算法基础"
difficulty: "进阶"
prerequisites: ["算法基础"]
tags: ["algorithm", "complexity"]
source: "算法设计与分析讲义"
source_url: "https://oi-wiki.org/basic/complexity/"
---

# 时间复杂度与空间复杂度

## 大 O 表示法
大 O 描述输入规模 `n` 增大时，算法资源消耗的增长趋势，关注最高阶项并忽略常数因子。

## 常见复杂度
- `O(1)`：常数时间
- `O(log n)`：二分查找
- `O(n)`：一次遍历
- `O(n log n)`：高效排序
- `O(n^2)`：双重循环
- `O(2^n)`：暴力枚举子集

## 分析方法
分别分析最坏、平均和最好情况，并结合数据结构操作成本。时间复杂度低不代表一定更快，常数、内存局部性和数据规模同样重要。
