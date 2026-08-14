# 开发日志

NewStart NZ — 奥克兰租金 × 治安 suburb 选区工具。

这份日志记录踩过的坑和当时为什么那么决定，按阶段而不是按天。真正花时间的从来不是画地图，
是让两套政府数据在地理上对得上。

---

## 阶段一：接上 MBIE API

新西兰商业创新就业部（MBIE）的 Market Rent API v2 提供官方租金统计。

```
https://api.business.govt.nz/gateway/tenancy-services/market-rent/v2
鉴权：Ocp-Apim-Subscription-Key 请求头
```

摸清楚的几件事：

- `area-definition` 有多个粒度，最细的是 `statistical-area-unit-2019`（SAU，统计区单元）。
  territorial-authority 粒度太粗，整个奥克兰才几行，没法做 suburb 级别的对比。
- SAU 粒度 + 12 个月滚动窗口是能拿到的最细数据，但请求慢——8,843 行、1.7MB，约 120 秒。
  小请求（TA 粒度、单月）是秒级的。
- 最新可用周期是 `period-ending=2025-12&num-months=12`。试过 `2026-03`，SAU 粒度直接返回 500，
  推测是 Bond Hub 迁移还没完成，粗粒度反而是通的。

字段里 `med`（中位数）、`mean`（平均数）、`lq`/`uq`（四分位）、`nCurr`（当前有效保证金数）都有用。
中途试过把展示值从 `med` 换成 `mean`，跑完看了下——Auckland Central 两居室 $705 → $719，
平均数被高端房源拉高，对「我能租到什么」这个问题反而失真，换回了 `med`。

---

## 阶段二：核心障碍——两套数据不共享地图

这是整个项目最花时间的部分，也是它真正的技术内容。

租金和治安数据都是公开且权威的，但**没人能把它们放一起看**，因为地理边界完全不同：

| 数据源 | 分区方式 | 例子 |
|---|---|---|
| MBIE 租金 | 统计区单元（SAU） | `Mount Eden East`、`Beach Haven West`、`Saint Heliers North` |
| NZ Police 治安 | 警方自己的分区 | `Maungawhau`、`Lynfield North`、`Beachhaven South` |
| 普通人说的 | suburb 名 | `Mt Eden`、`Beachhaven`、`St Heliers` |

三套命名互不重合。解决办法是建一层调和映射：两个 CSV，把 556 个租金源区域和 416 个警方源区域
逐个折叠到一组共用的 master suburb 上。

### 教训：地名不能当主键

这个坑反复踩了**四次**，每次表现都一样——某个 suburb 数据莫名其妙是空的：

| 次序 | suburb | 真实原因 |
|---|---|---|
| 1 | Mt Eden / Mt Albert / Mt Roskill | 源数据写 `Mount`，匹配写 `Mt`，模糊匹配失败 |
| 2 | Beachhaven | 源数据是 `Beach Haven`（两个词） |
| 3 | St Heliers | 源数据是 `Saint Heliers`（全拼） |
| 4 | Beachlands / Flat Bush | 源数据用完全不同的地名（`Maraetai`、`Sunkist Bay`、`Ormiston`）|

前三次都是同一类拼写变体问题。第四次不是拼写而是地名本身不同——Ormiston 是 Flat Bush 区域内的
一个中心，源数据只认 Ormiston。

**没有靠模糊匹配解决，全部改成显式映射表。** 模糊匹配在这个场景下是危险的：它会静默地漏掉，
而不是报错，你只有肉眼看到某个格子空了才会发现。映射表是穷举的，每一条都标 `mapped` 或
`not mapped` 并写原因，漏掉就一眼能看出来。

第一版映射做完之后，很多数字明显变了（Auckland Central 独立屋两居 $765 → $705，
公寓一居 $548 → $484）——说明之前的模糊匹配一直在拿错的区域算平均。

---

## 阶段三：交互结构

### 「All」放错了地方

最初 1B/2B/3B/4B 和 House/Apartment 两组按钮都带 All。这是错的：
**卧室数的「全部」没有意义**——把一居和四居的租金平均起来不对应任何真实的租房决策。
而房型的「全部」是有意义的：「两居室，独立屋或公寓都行，多少钱」是个正常问题。

改成 All 只出现在房型那一组，卧室数必须选一个具体值。

### 缺失数据显式暴露

有几个 suburb 在某个筛选组合下没有数据。填零或填均值都会骗人——填零会让它在「最便宜」
排行榜里排第一。统一显示 `No data`，并在推荐表里明确写出被排除了几个。

---

## 阶段四：可视化重构（四象限）

从「租金一张图、治安一张图」改成把两个维度同时呈现。

以**当前筛选下**的租金中位数和犯罪中位数为分界，把 suburb 分四类：

```
低租金 + 高安全 → Best value       #1D9E75
高租金 + 高安全 → Premium          #5B8DEF
低租金 + 低安全 → Budget           #EF9F27
高租金 + 低安全 → Not recommended  #E24B4A
```

关键点：**中位数随筛选重算**。切到四居室时租金中位数会整体上移，象限归属也跟着变——
象限描述的是「在这个价位段里的相对位置」，不是绝对标签。

配套加了并排散点图（X 轴租金、Y 轴对数犯罪数取反、点大小是保证金数量）和底部全宽推荐表。
散点图和地图双向联动：任意一边 hover 高亮另一边，点击同时选中并把地图 zoom 过去。

散点图用手写 SVG，没上图表库——项目一直是零构建的单文件 HTML，为了一张散点图引入
依赖不值得，而且 SVG 直接生成也就 80 行。

---

## 阶段五：上 GitHub

`scraper/.env` 里有 MBIE 的订阅密钥，迁移时做了三层检查：

1. 用密钥的**实际值**全盘 grep，确认只存在于 `.env`
2. 检查已 staged 的 blob 内容（不只是工作区文件）
3. 推送后拉 GitHub 上的实际文件树复核

`test_mbie_api.py` 用 `os.environ["MBIE_API_KEY"]` 读取，没有硬编码。补了根级 `.gitignore`
和 `.env.example`。commit 用 GitHub 的 noreply 邮箱，避免个人邮箱进 git 历史。

仓库设为 private——数据本身都是公开政府数据，但原型还在改，先不公开。

---

## 已知问题

按重要性排序。

### 1. 犯罪数是绝对值，不是人均

Auckland Central 4,914 起、Glendowie 25 起，但两者人口和人流量差了几个数量级。
现在的算法会**系统性地惩罚市中心和大型 suburb**，Auckland Central 永远落在
「Not recommended」象限。

要修需要引入各 suburb 人口数做标准化。这是目前最影响结论可信度的问题。

### 2. 「4 bed+ · Apartment」数据不可信

只有两个 suburb 有值：Onehunga $240/wk（n=12）、Auckland Central $269/wk（n=39）。
四居室公寓一周 240 块不可能，n=39 也说明不是小样本偶然波动——更像 MBIE 那边把按房间分租的
房源归进了这一类。

**没有擅自过滤掉**，因为那是在动源数据。但用户切到这个组合时看到的数字是错的。

### 3. 边界只是近似对齐

租金的 SAU 和警方分区形状本来就不一样，折叠到同一个 suburb 上必然有误差。
suburb 级数字是**指示性的，不是精确值**。

### 4. 覆盖率

62 个 suburb 涵盖 55,970 起案件，占全奥克兰 79,812 起的 70%。
剩下 30% 分布在外围区域（Papakura、Pukekohe、Waiheke 等），不在覆盖范围内。

### 5. Flat Bush 没有治安数据

租金已经通过 Ormiston 补上了，但警方数据里 Ormiston 被归到了 Botany。
没有改——把 Ormiston 的案件从 Botany 挪走会让 Botany 的数字失真，而且 Flat Bush 只拿到
一个警方分区的话本身也是低估，反而会让它错误地显示成「很安全」。宁可留空。

---

## 如果继续做

按投入产出排序：

1. **引入人口数据做人均犯罪率** — 唯一能实质提升结论可信度的改动
2. **样本量阈值提示** — nCurr 太低的格子标注「数据稀疏」，而不是当作可靠值展示
3. **suburb 详情页** — 现在 tooltip 里的「View details →」还没有落地页
4. **真实边界多边形** — 现在地图用的是圆点标记，有 GeoJSON 就能画真实 suburb 形状
5. **时间序列** — MBIE 有历史数据，可以做租金走势
