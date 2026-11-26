# 社区版画工坊套印台

公益工坊用这个本机服务制作社区活动的纪念版画。制版员从活动纸幅规格录入正反面定位格。印工用固定校样逐张实印，验收员把已完成的纸交给凭回执领件的装裱人员。逐纸记录让共用校样的纸可以独立补测和续印，也能查清哪些纸只做了正面。

## 运行

只需 Python 3.11 标准库。在项目根目录运行完整回归和演示。

```text
python3 -B check_project.py
python3 -B -m tests.support demo
```

控制台物化工程时提供 `check_project.py`。独立使用源码时，也可直接发现同一套测试。

```text
python3 -B -m unittest discover -s tests -t . -v
```

两个进程监听本机环回地址，数据库文件分开。下面的命令在两个终端运行，数据库路径应位于项目或其测试临时目录中。

```text
python3 -B -m press.runtime authoring --db authoring.sqlite --port 8101
python3 -B -m press.runtime station --db station.sqlite --port 8102
```

首启建立相应表。每次启动版务都会按固定键补齐 `examples/drafts.json` 中缺失的草稿。已有草稿及编辑内容原样保留。演示从 `examples/workday.json` 取纸号和观测，通过真实 HTTP 调用完成办理，使用隔离临时数据库。

## 一天的办理顺序

1. 制版员把纸幅规格与定位图交给草稿入口，可在冻结前修订。
2. 制版员从草稿或直接提交的版样冻结版次，取得可查的固定版号。
3. 制版员预览标称套合并签发固定件，可同时登记小修版。印工向工作台交付整件并核对校样号及版号。
4. 印工按已装载校样登记纸号，实印正面并取得实际位置和印次号。
5. 印工读取纸边或顶标，只缩小产生读数的那张纸的可能方向。
6. 印工为双面纸请求一条反印指令，待定位时可补测后续印。工作台可在版务进程关闭时办理。
7. 印工发现正面缺墨时，按原实印号提交缺墨读数，领取修单逐项补印；补测缩小纸向后可换新修单。
8. 验收员按纸号集合核对实际印次，保存合格明细与未完项。
9. 装裱人员按号领验收件。后续补印可另办验收，旧号仍返回当时清单。

## 位置和办理规则

纸幅坐标为 `0 <= x < width` 和 `0 <= y < height`。规格使用 `width`、`height`、`sides` 和 `faces` 四个字段，例如 `{"width":5,"height":3,"sides":"double","faces":{"front":[[1,1]],"back":[[1,1]]}}`。`single` 使用正面图，`double` 使用正反面图。冻结拒绝缺图、空图、非整数格或越界格。定位图按不同格点组成的集合处理，固定按 `(x,y)` 排序。

正面档 P、S、Q 的横移量依次为 0、+1、+2 格。反面也可请求横移 −1 格的 R 档。左向对所有格点应用横移。右向在同样的横移后把每个 `x` 换成 `width - 1 - x`。任何格移出纸幅就使该放置无效。校样以 P 档产生的正面为标称基准。双面校样只要至少一向存在成功的反印档就可签发，实际续印使用实际正面。验收比较规范坐标中的整张定位图。

`edge` 读数使用左向的 `[0,0]` 或右向的 `[width-1,0]`。`top` 使用左向的 `[width//2,0]` 或对应的镜像点。若两向读数相同，该读数可保留两向。每张纸从两向开始，接纳读数逐次取交集。矛盾读数无写入。

一个反印请求只执行一条指令。该指令须对本纸所有剩余方向套合。无共同指令且还有至少一个可行方向时返回 `needs_orientation`。剩余方向均无解，或有共同指令但请求未选中时，返回 `incompatible`。拒绝保留正面实印和续印资格。读取正面、定位、计算资格及插入反面均在同一工作台写入事务中完成。每张纸每面最多一个实印。成功反印记录实际正面印次号。

## 缺墨补印

正面实印偶尔只坏几格时，工坊用登记过的小修版在台面上补墨，修好的纸仍按原实印出处交付装裱。版务在签发校样时随件冻结补印登记 `repair`：允许补印的格 `repairable`、不可再落墨的格 `forbidden`，以及按登记顺序排列的小修版 `plates`（每版给出定位 `position` 与实际覆盖的格 `cells`，至多 60 版）。登记随校样信封一并固定、校验与装载。

印工按正面原实印号提交缺墨格读数（每张至多 20 格）。工作台对每个仍可能的纸向分别解释读数（右向按 `width-1-x` 镜像），并寻找同一组台面补印动作：各可能纸向的缺墨格都恰好补一遍，且任何一向都不碰仍完好或禁止再印的格。可行组取动作数最少者，同数按校样登记顺序比较动作号。判定与修单一并签发；无解判定同样留存，供验收冻结无解纸。修单绑定实印号、定位读数和每个动作对各可能纸向的覆盖。

逐项实做：同号动作重复领取返回首次实印，不增加墨层。补测缩小纸向后可换新修单，已实做的动作作为实印继续保全，其覆盖从新的剩余需求中扣除；定位状态变化后，旧修单的迟到命令不再算作实印。批次验收复用原印次和补印首执，分别冻结已完成、待补（`repair_pending`）与无解（`repair_unsolvable`）各纸及缺墨出处；重开后原验收与补印首执仍可复领。无缺墨的套印路径照常。

## HTTP 接口

请求体使用 `application/json` 对象。用户指定的草稿和纸号使用 1–80 个 ASCII 字母、数字、连字符或下划线，首字符为字母或数字。版号、校样号和验收号由服务分配。表内的花括号表示路径参数或请求字段。

| 模式 | 请求 | 输入及结果 |
|---|---|---|
| 版务 | `PUT /drafts/{draft_id}` | `{spec}`，更新草稿并返回纸幅规格。可保存待修订的图，冻结时校验。 |
| 版务 | `GET /drafts/{draft_id}` | 读取草稿。 |
| 版务 | `POST /editions` | `{draft_id}` 或 `{spec}`，冻结快照并返回 `edition_id`。 |
| 版务 | `GET /editions/{edition_id}` | 读取原冻结版次。 |
| 版务 | `GET /editions/{edition_id}/check` | 返回标称正面、各方向可用档及 `eligible`。 |
| 版务 | `POST /proofs` | `{edition_id}` 或 `{edition_id,repair}`，签发并返回固定校样件。 |
| 版务 | `GET /proofs/{proof_id}` | 按校样号重领签发件。 |
| 工作台 | `POST /proof-loads` | `{proof_id,edition_id,artifact}`，其中 `artifact` 是整个签发响应。复载同件返回 200。 |
| 工作台 | `GET /proof-loads/{proof_id}` | 读取本地固定件。 |
| 工作台 | `POST /sheets` | `{sheet_id,proof_id}`，登记实际纸。 |
| 工作台 | `GET /sheets/{sheet_id}` | 查看本纸校样、方向和已接纳的原始读数。 |
| 工作台 | `POST /observations` | `{sheet_id,probe,point}`，追加读数，返回读数号和剩余方向。 |
| 工作台 | `POST /impressions` | `{sheet_id,face,command}`，成功时返回实印号、位置及其正面来源。 |
| 工作台 | `GET /impressions/{sheet_id}` | 查看本纸实际印次，按提交顺序。 |
| 工作台 | `POST /repair-orders` | `{sheet_id,impression_id,readings}`，判定并签发修单，无解亦留存。 |
| 工作台 | `GET /repair-orders/{order_id}` | 复领修单及已实做动作。 |
| 工作台 | `POST /repair-executions` | `{order_id,action_no}`，实做一项；同号复领返回首执。 |
| 工作台 | `GET /repair-executions/{repair_id}` | 按号复领补印首执。 |
| 工作台 | `POST /acceptances` | `{sheet_ids:[...]}`，冻结合格与未完清单。空清单可验收。 |
| 工作台 | `GET /acceptances/{acceptance_id}` | 返回原验收件。 |

校样信封为 `{version,body,digest}`。版本为 1，正文绑定校样号、版号、固定布局和标称逐向摘要。`digest` 校验使用排序键、紧凑分隔符和 ASCII 转义的 JSON 正文的 SHA-256，供本机文件交接检查内容一致性。装载另查请求声明与正文出处。拒绝错配及同号异件，保留原装载件。

新增记录返回 201，读取及草稿更新返回 200。错误体包含 `error` 和 `message`。HTTP 400 表示请求格式错误，404 表示本模式无该路径或所指对象不存在，422 表示定位图、定位点、交件、印刷参数或补印登记无效。HTTP 409 表示与现有事实不相容，如 `initial_incompatible`、`proof_origin_mismatch`、`proof_conflict`、`sheet_exists`、`conflicting_observation`、`invalid_sequence`、`already_printed`、`needs_orientation`、`incompatible`、`duplicate_sheet`、`repair_not_registered`、`impression_mismatch`、`repair_unsolvable`、`order_superseded` 或 `stale_order`。

验收时从同一事务内读取整批实际印次。单面核对一次有效正面，双面核对同一纸及校样的两面、正面关联和套合位置。合格与未完清单分别按纸号排序，重复或未知纸号使整批拒绝。合格明细保存版号、校样号及实印来源。

## 样例结果

五列纸幅的中心格 `(2,1)` 用 P 档时两向都原位，CENTER 可直接续印。偏左格 `(1,1)` 在左向用 P，在右向要用 Q。EAST 用 P 首次请求会待定位，补左向读取后 Q 被拒，再用 P 成功。WEST 此时仍未完。首次验收包含 CARD、CENTER、EAST 三张，WEST 为未完。WEST 补右向读取并执行 Q 后可另办验收，重启后的首次回执内容保持原样。

演示随后办理三组补印。GREEDY 的候选中覆盖三格的动作是贪心首选，但留下一格无可再补，修单按最少动作签出两版组合。SPLIT 的缺墨读数在左向可用动作 1、在右向可用动作 2，两向各有解但没有共同动作组，判为无解；任一方向补测缩小后分别可解。HALF 实做一个动作后补测换单，旧单迟到命令被拒，新单只补剩余一格，验收引用两次补印首执，重启后回执与首执均可复领。
