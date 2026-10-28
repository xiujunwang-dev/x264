#!/usr/bin/env python3
"""Write the Chinese x264 results and concrete submission handoff."""
import json
from pathlib import Path

from helpers import save

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1] if HERE.parent.name == 'research' else HERE


def percent(x, digits=2):
    if abs(x) < .5 * 10 ** -digits:
        x = 0.0
    return f'{x:+.{digits}f}%'


def main():
    d = json.loads((HERE / 'summary.json').read_text())
    author = json.loads((HERE / 'author_information.json').read_text())
    publication = json.loads((HERE / 'publication.json').read_text())
    assert d['counts']['jobs'] == 147
    k, e, counts = d['aggregate_replay'], d['aggregate_end_to_end'], d['counts']
    primary = k['2']['envelope']
    lines = [
        '# x264 时域滤波实验与投稿评估', '',
        f"作者：{author['name']}；单位：{author['affiliation']}；单作者。目标期刊：IEEE Signal Processing Letters。", '',
        f"通信邮箱：{author['email']}；ORCID：{author['orcid']}。作者声明无相关既有成果。", '',
        '本次已将滤波和参考省略机制移植到官方 x264，并重新完成编码、逐像素回放和消融实验。'
        '论文的技术核心是固定整数时域滤波器的误差证书，以及更强的保留参考分母包络判据。'
        '已按作者决定准备投稿文件；三篇最接近论文的全文公式比较暂缓，不能据此认定创新性已经核实。'
        '期刊尚未收到本稿，作者独立科学核查和最终投稿声明尚未记录为完成。', '',
        '## 官方 x264 平台', '',
        '源码来自 VideoLAN 官方 x264 r3223，提交 '
        '`0480cb05fa188d37ae87e8f4fd8f1aea3711f7ee`。官方原版和扩展版分别构建；'
        '关闭 MCTF 时的码流与官方版本逐字节一致。平台切换后的全部性能数值均重新测量。'
        '补丁包含独立的 MCTF 运动场、命令行开关、完整源码哈希及版本固定脚本。', '',
        '测试平台为原生 ARM64 Apple M1、Apple clang 21、8 bit 4:2:0。MCTF 只处理 I/P 帧亮度；'
        '滤波 QP=27，I/P 强度为 1.05/0.63，完整窗口为 I=3、P=2，缩窗为 I=2、P=1。'
        '扩展默认关闭，原始低分辨率 lookahead 图像与共享运动代价缓存保持原算法使用方式。', '',
        '## 新判据与实现优化', '',
        '离散支持函数把像素差值与实际 LUT 权重绑定，避免分别取最大差值和最大权重造成的松界。'
        '保留参考的位移上界由有限分式规划求得；Dinkelbach 方法本身属于已有方法，稿件已引用。', '',
        '新增的分母包络保留了“较大位移需要较大归一化权重”的关系。它把位移范围划分成 16 个区间，'
        '用 8 个固定斜率构造分母下界，再检查每个区间。数学上，它包含原紧半径支持判据的全部可接受集合；'
        '给出的稀疏整数表反例证明包含可以严格成立。交叉乘积使用 128 bit 整数。'
        '这证明了判据相对于该基线的加强，文献层面的优先性仍取决于最接近工作的全文比较。', '',
        '八像素 NEON 融合属于独立工程优化。它保持 LUT 与精确整数归一化，四像素与八像素版本的所有'
        '完整编码曲线码流均一致。所有主要省略方法统一采用八像素内核，避免混入内核差异。', '',
        '## 冻结实验', '',
        '主实验使用完整 1080p Blue Sky 217 帧、Pedestrian Area 375 帧、Crowd Run 500 帧，共 1092 帧。'
        'Foreman、Mobile 和 Old Town 用于开发。上述六段内容此前均已观察过，因此本轮属于 x264 平台复现实验，'
        '不称为从未观察过的独立确认集。新一轮曲线与回放结果产生前已固定参数、方法、顺序与聚合方式。', '',
        f"共完成 {counts['jobs']} 次完整编码，其中 {counts['formal_jobs']} 次正式编码；每个方法均有 CRF 22/27/32/37 "
        '四点曲线和 3 次 CRF 27 正式计时。完整进程时间包含启动与源文件读取；码率失真使用相对原始视频的精确 SSE、'
        'PSNR Y 和共同质量区间内的 PCHIP BD rate，不外推。', '',
        f"采集 {counts['filtered_frames']} 个被滤波帧，逐像素回放 τ=1、2、3，每个方法和容限审核 "
        f"{counts['audit_pixels_per_method_and_tolerance']:,} 个像素。回放包含规划、运动补偿与融合，运动场由完整滤波采集提供；"
        '省略运动搜索的收益只进入完整编码计时。每个内容先取配对变化的中位数，再对三个内容等权平均。', '',
        '## 主容限的滤波结果', '',
        '下表均以相同八像素完整滤波为基线，τ=2。负时间变化表示更快；负工作量变化表示省略了更多补偿块。', '',
        '| 方法 | 滤波时间变化 | 参考块工作量变化 | 最大像素差 | 越界像素数 |',
        '| --- | ---: | ---: | ---: | ---: |']
    names = {'moment': '分别取极值', 'joint': '简单半径支持', 'support': '紧半径支持',
             'envelope': '新增分母包络', 'window_real': '直接缩窗并重建 LUT', 'window_checked': '缩窗并完整计算校验'}
    for m in names:
        v = k['2'][m]
        lines.append(f"| {names[m]} | {percent(v['mean_time_percent'])} | {percent(v['mean_work_percent'])} | {v['max_error']} | {v['violations']:,} |")
    lines += ['', '## 新判据的增量收益', '',
              '| 容限 | 包络相对紧半径的配对时间变化 | 额外省略的参考块数 |',
              '| --- | ---: | ---: |']
    for t in [1, 2, 3]:
        c = k[str(t)]['comparisons']
        lines.append(f"| {t} | {percent(c['envelope_vs_support']['mean_time_percent'])} | {c['envelope_extra_omitted_tiles']:,} |")
    extra = k['2']['comparisons']['envelope_extra_omitted_tiles']
    incremental = ('τ=2 在三个主内容上均未比紧半径额外省略参考，因此主容限下不能声称新增包络省略更多。'
                   if extra == 0 else f'τ=2 相比紧半径额外省略 {extra:,} 个参考块。')
    lines += ['', '该表保留三个已冻结容限的全部结果。' + incremental +
              '判据更强也不保证实际时钟时间更短，额外判定本身有开销。所有认证方法在全部容限下均未出现误差越界。', '',
              '## 完整编码结果', '',
              '下表以完整 MCTF 为基线。它评估实际编码过程，不把滤波像素误差界当作最终解码误差界。', '',
              '| 方法 | BD rate 变化 | CRF 27 完整进程时间变化 |',
              '| --- | ---: | ---: |']
    enames = {'full': '完整 MCTF 八像素', 'extrema': '分别取极值', 'support': '紧半径支持',
              'envelope': '新增分母包络', 'window1': '实际缩窗', 'full4': '完整 MCTF 四像素', 'off': '官方 x264 关闭 MCTF'}
    for m, name in enames.items():
        v = e[m]
        lines.append(f"| {name} | {percent(v['mean_bd_rate_percent'], 3)} | {percent(v['mean_crf27_time_percent'])} |")
    lines += ['', '新增分母包络在每个主内容上的结果如下，均以八像素完整 MCTF 为基线，容限为 2。', '',
              '| 内容 | 滤波时间变化 | 完整编码时间变化 | BD rate 变化 |',
              '| --- | ---: | ---: | ---: |']
    snames = {'blue_sky': 'Blue Sky', 'pedestrian': 'Pedestrian Area', 'crowd': 'Crowd Run'}
    for source in d['sources']:
        kernel = source['replay']['2']['methods']['envelope']['median_percent']
        encode = source['end_to_end']['crf27_timing']['envelope']['median_percent']
        bdr = source['end_to_end']['bd_rate']['envelope']['percent']
        lines.append(f"| {snames[source['id']]} | {percent(kernel)} | {percent(encode)} | {percent(bdr, 3)} |")
    lines += ['', f"相对无 MCTF 的官方 x264，完整 MCTF 的平均 BD rate 为 {percent(e['full']['mean_bd_rate_vs_off_percent'], 3)}，"
              f"完整进程时间为 {percent(e['full']['mean_crf27_time_vs_off_percent'])}。这组基线明确区分滤波自身的影响与省略参考的收益。", '',
              f"八像素完整内核相对四像素完整内核，回放时间变化 {percent(k['2']['comparisons']['eight_vs_four']['mean_time_percent'])}，"
              f"完整编码时间变化 {percent(d['comparisons']['eight_vs_four'])}。输出保持一致，因此该项归为工程优化。", '',
              '## 正确性与适用范围', '',
              '支持与包络单元测试完成 341,260,850 次穷举比较和 4,000,000 次随机比较；八像素内核另有 12,000 个块、'
              '829,099 个标量像素比较和 147,200 个边界像素比较，覆盖未对齐、尾部、原地写入和回退。'
              '这些单元测试均通过 ASan 和 UBSan。112 次完整集成编码与 4 次整编码器 ASan 检查通过。'
              '整编码器未声称通过 UBSan：官方既有未对齐访问会先触发该检查。', '',
              '保证对象是在相同 anchor、参考、运动场和完整 LUT 下，近似滤波输出与完整滤波输出的逐像素整数差。'
              '完整编码器可能改变后续码率控制、模式决策与帧轨迹，不能据此保证最终重建误差。'
              '三个主内容、一个处理器和固定权重限制了性能外推；计时重复也不等于内容层面的显著性检验。', '',
              '## 投稿文件与待核实事项', '',
              'EMCTF 2024、CAMCTF 2025 和 SPL 2015 Quantitative Error Analysis of Bilateral Filtering '
              '的全文公式对照尚未完成，作者决定暂缓该检查并先准备投稿。公开摘要已用于限定引用范围，不能用来断言不存在相同判据。'
              'EMCTF 相关博士论文已找到官方入口，但全文有手动版权确认门，尚未作为全文证据使用。', '',
              '作者已提供独立研究者身份、通信邮箱与 ORCID，确认单作者及无相关既有成果。'
              '城市和国家尚未提供，若投稿系统要求需填写真实信息。作者独立检查证明、实验和英语表述以及排他投稿声明尚未记录为完成。'
              '主文已声明 AI 辅助范围。最终 Submit 应使用作者实际登录的官方 Author Portal，并保存稿件编号。', '',
              (f"代码与复现证据已发布：{publication['branch_url']}。固定代码快照：{publication['code_url']}。"
               if publication['published'] else 'GitHub 研究分支与复现包正在准备；尚未记录为发布成功。'), '',
              '稿件与复现材料见本目录 `manuscript/`、`summary.json`、`literature_audit.json`、'
              '`REPRODUCE.txt`、`x264_mctf.patch`。最终 PDF 位于 `output/pdf/`。', '']
    report = '\n'.join(lines)
    (HERE / 'x264_report_zh.md').write_text(report)
    output = ROOT / 'output'
    output.mkdir(exist_ok=True)
    (output / 'mctf_x264_report_zh.md').write_text(report)
    readiness = dict(author='Xiujun Wang', platform='Official x264 r3223 plus native MCTF extension',
                     experiments_completed=True, complete_encodes=counts['jobs'],
                     local_review_draft=True, submission_files_prepared=True,
                     submitted=False, globally_novel_claim_verified=False,
                     author_information=author, code_publication=publication,
                     deferred_by_author=['Equation-level comparison of EMCTF2024/CAMCTF2025/SPL2015 full texts'],
                     remaining=['Author independent scientific and English review',
                                'City/country if required by the submission portal',
                                'Author final approval and exclusive-submission declarations in the portal'],
                     improvements=dict(primary_kernel_time_percent=primary['mean_time_percent'],
                                       primary_work_percent=primary['mean_work_percent'],
                                       primary_full_process_time_percent=e['envelope']['mean_crf27_time_percent'],
                                       primary_bd_rate_percent=e['envelope']['mean_bd_rate_percent']))
    save(HERE / 'readiness.json', readiness)
    print(output / 'mctf_x264_report_zh.md')


if __name__ == '__main__':
    main()
