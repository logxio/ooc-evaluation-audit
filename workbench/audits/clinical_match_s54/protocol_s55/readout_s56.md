# Clinical Linkage and Fixed Budget Donor Reallocation

248 matched cancer patients contribute to the clinical evidence set, including 243 patients with numerical sensitivity measurements. Eight study clusters meet the two patients per outcome class criterion. Within study pair weighted AUC is 0.950250, with a 10,000 replicate study and patient bootstrap interval of [0.684879, 0.977458]. The complete exposure analysis includes 185 patients across five clusters, AUC 0.961456.

## 身份与队列

Chen原表核出78个药筛样本、74个患者ID。样本P编号后缀与78个PDO列逐一对应。Pat105有P105/P106，Pat063有P063/P120/P130，Pat084有P084/P147。逐例按患者、样本与PDO连接；一个患者保留最早可评价的采样后治疗。该表可识别125个不同Pat编号，格式化工作表行数单独计数。bridge_v1.json保留原字节与SHA链，bridge.json和bridge_receipt_s58.json记录本轮映射。

主分析响应类为来源临床获益（含SD）或术后随访未复发，结局逐例保留；该AUC包含不同结局家族。联合方案成分均值、活性代谢物、药物类似物冲突分别标记。Chen的PFS时长项使用≥6个月的回顾性扩展，单列剔除敏感性。此项研究重分析与前瞻性验证分别计数。

|研究DOI|数值患者|获益/未获益|研究内AUC|
|---|---:|---:|---:|
|10.1002/advs.202204097|23|13/10|0.876923|
|10.1016/j.xcrm.2023.101335|13|3/10|0.750000|
|10.1016/j.xcrm.2025.102397|127|58/69|0.966267|
|doi:10.1371/journal.pone.0339416|1|1/0|NaN（单类别）|
|10.1016/j.xcrm.2023.101277|9|6/3|0.833333|
|10.1038/s41467-021-22676-1|9|6/3|1.000000|
|10.1002/advs.202101176|14|8/6|0.833333|
|10.1186/s12885-025-15495-x|7|3/4|0.833333|
|10.1002/1878-0261.13296|40|36/4|0.670139|

完整暴露或活性基团矩阵敏感性：185人数值可联，5个簇，AUC=0.961456，区间=[0.7452830188679245, 0.9844128743106545]。主分析8簇使用明确标记的成分代理扩展；完整暴露口径按自己的5簇读数计。

Hu的LC134/LCO134别名由Par19与Fig6c表头闭合，Par18/Fig6a证明PC与GC按1:1联合暴露。LC127临床Pem单药而数值曲线为PC，按成分代理记录；LC133正文ecotinib、临床表Gef，按类似物冲突记录。四例辅助DFS保留为随访结局。

BMC7例逐人核对手术早于评估日期；统一使用实际治疗对应单药AUC或所有已测成分算术均值，AUC为0.833333。Molecular Oncology使用作者发布的首线方案分数，按原文排除049、055、046、163及无治疗患者，共40人；bevacizumab和CCRT缺失成分逐例标记。Tan即时无单抗FOLFOX共5例，1人与既有后线TAS102患者重叠，按即时方案归并，最终13人、3/10。

## 同预算Monte Carlo

每研究/预算/策略10000次配对模拟；每预算每种汇总10000次研究及类别内患者bootstrap。主分析A为n>(W minus 6)//30的非饱和研究，主分析B为统一预算的多中心工作列表。原全研究pair-weighted结果、等研究权重敏感性与每研究孔位闲置均保留。

|口径|孔数|D_sparse ΔAUC [95% CI]|D_gate ΔAUC [95% CI]|D_gate_adaptive ΔAUC [95% CI]|
|---|---:|---|---|---|
|非饱和|96|+0.028596 [+0.022577, +0.134789]|-0.001462 [-0.005683, +0.016184]|-0.000784 [-0.003041, +0.012388]|
|多中心共享|96|+0.012329 [+0.004685, +0.014258]|-0.000728 [-0.001485, +0.001379]|-0.000446 [-0.001118, +0.001008]|
|全部研究pair-weighted|96|+0.028596 [+0.022590, +0.135148]|-0.001462 [-0.005317, +0.015649]|-0.000784 [-0.002930, +0.012459]|
|全部研究等权|96|+0.106325 [+0.050641, +0.162181]|+0.006755 [-0.014366, +0.028592]|+0.006748 [-0.008828, +0.022335]|
|非饱和|192|+0.057683 [+0.034329, +0.140155]|+0.006586 [+0.001617, +0.049143]|+0.008071 [+0.004308, +0.044338]|
|多中心共享|192|+0.028742 [+0.010455, +0.032707]|+0.002603 [-0.000124, +0.006286]|+0.003429 [+0.000871, +0.005716]|
|全部研究pair-weighted|192|+0.057683 [+0.036077, +0.142812]|+0.006586 [+0.001636, +0.049948]|+0.008071 [+0.004390, +0.045024]|
|全部研究等权|192|+0.064618 [+0.015655, +0.115227]|+0.027428 [+0.000504, +0.054600]|+0.026510 [+0.002161, +0.049923]|
|非饱和|384|+0.099403 [+0.006573, +0.112201]|+0.008994 [-0.011008, +0.042661]|+0.012057 [-0.004970, +0.039248]|
|多中心共享|384|+0.057228 [+0.022429, +0.064769]|+0.004955 [+0.000082, +0.012179]|+0.006327 [+0.001904, +0.010873]|
|全部研究pair-weighted|384|+0.097877 [-0.011564, +0.110607]|+0.008695 [-0.015276, +0.036310]|+0.011681 [-0.011202, +0.033401]|
|全部研究等权|384|+0.013211 [-0.034282, +0.061488]|+0.000300 [-0.022501, +0.023277]|-0.000516 [-0.024465, +0.022102]|

预算按D_dense每供体30孔/控制6孔、D_sparse每供体9孔/控制12孔、门控每次18孔且最多重测一次计算。多中心统一工作列表和孔位预算，排序与临床正负对保持研究内。所有策略使用固定0.5未测先验，覆盖抽取按与临床标签无关的随机顺序。

J1原908曲线6155子集的百分位噪声模型按SHA复用。该模型以百分位噪声迁移到IC50、矩阵与序数分数；双读数相关性主值0，相关性1作为敏感性分析。多中心模拟共享控制孔，启动孔、桥接孔与培养失败率设为0。

## LOSO与验收

|留出研究|预测AUC|未再校准概率的校准斜率|Brier|
|---|---:|---:|---:|---:|
|10.1002/advs.202204097|0.876923|1.124280|0.137533|
|10.1016/j.xcrm.2023.101335|0.750000|0.548319|0.326179|
|10.1016/j.xcrm.2025.102397|0.966267|3.874099|0.165443|
|10.1016/j.xcrm.2023.101277|0.833333|0.891803|0.154586|
|10.1038/s41467-021-22676-1|1.000000|30.415884|0.083999|
|10.1002/advs.202101176|0.833333|0.875102|0.140612|
|10.1186/s12885-025-15495-x|0.833333|0.890185|0.198875|
|10.1002/1878-0261.13296|0.670139|0.271482|0.357809|

每次整研究留出，逻辑模型和阈值在其它研究拟合。研究内percentile参照同测面板，属于无结局转导参照。heldout预测在各研究内重采样10000次，拟合每个留出研究执行一次，bootstrap中固定该预测。Brier给出均值偏差、预测方差、结局方差与协方差精确分解。异质物理单位的跨研究绝对斜率以不可识别及具体原因记录。

## Data and Recalculation

[Patient records](j3_expanded_cohort.json) contain the numerical clinical cohort. [Clinical and LOSO results](j3_expanded_loso.json) contain study level estimates, held out predictions, bootstrap intervals and exposure sensitivities. [Fixed budget results](j2_budget_monte_carlo.json) contain the 10,000 paired Monte Carlo draws summarized by study, budget and design.

The 96 well budget with 3 wells per donor gives a nonsaturated cohort AUC increase of +0.160506. The 9 well design gives +0.028596, +0.057683 and +0.099403 at 96, 192 and 384 wells. Each estimate uses the same budget and its stated control well allocation.

Within study AUC compares every favourable and unfavourable patient pair, with lower sensitivity scores predicting favourable outcomes. Summing correctly ranked pairs and dividing by all within study pairs reproduces the pooled estimate. LOSO holds out each complete study, fits on the other studies and scores the held out patients.

The portable verifier recomputes both AUC estimates and their 10,000 draw study and patient bootstrap intervals, checks held out predictions and the Brier identity, and reaggregates the released 10,000 draw Monte Carlo summaries by their within study pair counts.

```sh
python verify_s57.py
```
