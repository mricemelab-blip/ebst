#!/usr/bin/env python3
"""Convert SBST docx courseware to HTML chapter files."""

import re
import os
from docx import Document
from docx.oxml.ns import qn
from html import escape as html_escape

# ============================================================
# CONFIG: Map docx sections → website chapters
# ============================================================
CHAPTER_MAP = [
    # (ch_num, docx_section_title_short, full_title_en, subtitle_zh, para_start, para_end_exclusive)
    (1, '§4', 'Lat Pulldown & Straight-Arm Pulldown', '高位下拉与直臂下压', 0, 202),
    (2, '§5', 'Pull-Up', '引体向上', 202, 363),
    (3, '§6', 'Row', '划船', 363, 492),
    (4, '§7', 'Face Pull', '面拉', 492, 599),
    (5, '§8', 'Overhead Press', '肩推', 599, 773),
    (6, '§9', 'Bench Press', '卧推', 773, 987),
    (7, '§10', 'Split Squat', '分腿蹲', 987, 1108),
    (8, '§11', 'Squat', '深蹲', 1108, 1289),
    (9, '§12', 'Plank & Push-Up', '平板支撑与俯卧撑', 1289, 1464),
    (10, '§13', 'Arms & Deltoids', '臂部与三角肌', 1464, 1637),
]

SBST_DIR = '/Coze/Drive/Arise/所有对话/主对话/3HFIT/教培中心/sbst'
DOCX_PATH = '/Coze/Drive/Arise/全教材v5_科学修订版_1790942165163_b1bs.docx'


def html_esc(text):
    return html_escape(text) if text else ''


def process_inline_formatting(text):
    """Convert inline markdown-like formatting to HTML."""
    text = html_esc(text)
    # Bold: **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
    # Italic: *text* or _text_ (but not inside bold)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
    # DOI links
    text = re.sub(r'(10\.\d{4,}/[^\s<]+)', r'<a href="https://doi.org/\1" target="_blank" style="color:var(--accent);text-decoration:underline">doi:\1</a>', text)
    return text


def convert_table_to_html(table):
    """Convert a docx table to HTML table."""
    rows = []
    for ri, row in enumerate(table.rows):
        cells = []
        for cell in row.cells:
            cell_text = cell.text.strip()
            tag = 'th' if ri == 0 else 'td'
            cells.append(f'<{tag}>{process_inline_formatting(cell_text)}</{tag}>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')
    
    return f'''<div class="lecture-table-wrap"><table class="lecture-table">
{''.join(rows)}
</table></div>'''


def build_lecture_html(paragraphs_data):
    """Convert paragraph list to lecture HTML content.
    paragraphs_data: list of (style, text) tuples
    """
    html_parts = []
    in_list = False
    
    for style, text in paragraphs_data:
        if not text.strip():
            continue
        
        text = text.strip()
        
        # Determine heading level
        if 'Heading 2' in style:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(f'<h3 class="lecture-h3">{process_inline_formatting(text)}</h3>')
        elif 'Heading 3' in style:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(f'<h4 class="lecture-h4">{process_inline_formatting(text)}</h4>')
        elif 'Heading 4' in style:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(f'<h5 class="lecture-h5">{process_inline_formatting(text)}</h5>')
        elif 'Blockquote' in style or style == 'Quote':
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(f'<blockquote class="lecture-blockquote">{process_inline_formatting(text)}</blockquote>')
        elif text.startswith('•') or text.startswith('- ') or text.startswith('·'):
            # List item
            bullet_text = text.lstrip('•-· ').strip()
            if not in_list:
                html_parts.append('<ul class="lecture-list">')
                in_list = True
            html_parts.append(f'<li>{process_inline_formatting(bullet_text)}</li>')
        elif re.match(r'^[\d]+[\.\)]\s', text):
            # Numbered list
            if not in_list:
                html_parts.append('<ol class="lecture-olist">')
                in_list = True
            html_parts.append(f'<li>{process_inline_formatting(text)}</li>')
        else:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(f'<p class="lecture-p">{process_inline_formatting(text)}</p>')
    
    if in_list:
        html_parts.append('</ul>')
    
    return '\n'.join(html_parts)


def extract_sections_with_tables(doc, ch_start, ch_end):
    """Extract paragraphs AND tables for a chapter section, in document order."""
    # We need to iterate through body elements to get interleaved paragraphs and tables
    paragraphs_data = []
    tables_html = []  # (position_index, html)
    
    para_idx = 0
    elem_idx = 0
    body = doc.element.body
    
    # First, collect all paragraphs with their global index
    all_paras = []
    for p in doc.paragraphs:
        all_paras.append(p)
    
    # Build mapping from paragraph element to index
    para_elem_to_idx = {}
    for i, p in enumerate(all_paras):
        para_elem_to_idx[p._element] = i
    
    # Collect table elements
    table_elem_to_table = {}
    for t in doc.tables:
        table_elem_to_table[t._element] = t
    
    # Iterate body children in order
    target_paras = []
    target_tables_at = {}  # para_idx -> list of table HTMLs that follow this para
    
    current_para_idx = -1
    last_para_idx_before_table = -1
    
    for child in body:
        if child.tag == qn('w:p'):
            if child in para_elem_to_idx:
                current_para_idx = para_elem_to_idx[child]
                if ch_start <= current_para_idx < ch_end:
                    p = all_paras[current_para_idx]
                    target_paras.append((p.style.name, p.text))
                    last_para_idx_before_table = current_para_idx
        elif child.tag == qn('w:tbl'):
            if child in table_elem_to_table:
                if current_para_idx >= ch_start and current_para_idx < ch_end:
                    tbl_html = convert_table_to_html(table_elem_to_table[child])
                    # Insert after the last paragraph we saw
                    if target_paras:
                        # We'll insert the table HTML as a special marker
                        target_paras.append(('__TABLE__', tbl_html))
    
    # Build final HTML
    html_parts = []
    in_list = False
    
    for style, text in target_paras:
        if style == '__TABLE__':
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(text)  # Already HTML
            continue
        
        if not text.strip():
            continue
        
        text = text.strip()
        
        # Skip the top-level chapter title (§X 单元X：...) for first heading
        if 'Heading 2' in style and text.startswith('§') and target_paras.index((style, text)) == 0:
            continue
        
        if 'Heading 2' in style:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(f'<h3 class="lecture-h3">{process_inline_formatting(text)}</h3>')
        elif 'Heading 3' in style:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(f'<h4 class="lecture-h4">{process_inline_formatting(text)}</h4>')
        elif 'Heading 4' in style:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(f'<h5 class="lecture-h5">{process_inline_formatting(text)}</h5>')
        elif 'Heading 1' in style:
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(f'<h3 class="lecture-h3">{process_inline_formatting(text)}</h3>')
        elif 'Blockquote' in style or style == 'Quote':
            if in_list:
                html_parts.append('</ul>')
                in_list = False
            html_parts.append(f'<blockquote class="lecture-blockquote">{process_inline_formatting(text)}</blockquote>')
        elif text.startswith('•') or text.startswith('- ') or text.startswith('·'):
            bullet_text = text.lstrip('•-· ').strip()
            if not in_list:
                html_parts.append('<ul class="lecture-list">')
                in_list = True
            html_parts.append(f'<li>{process_inline_formatting(bullet_text)}</li>')
        elif re.match(r'^[\d]+[\.\)]\s', text):
            if in_list:
                html_parts.append('</ul>')
                in_list = False
                html_parts.append('<ol class="lecture-olist">')
                in_list = True  # reuse flag for ol
            html_parts.append(f'<li>{process_inline_formatting(text)}</li>')
        else:
            if in_list:
                html_parts.append('</ol>')
                in_list = False
            html_parts.append(f'<p class="lecture-p">{process_inline_formatting(text)}</p>')
    
    if in_list:
        html_parts.append('</ol>')
    
    return '\n'.join(html_parts)


def generate_sop(ch_num, title, content_text):
    """Generate SOP worksheet HTML from chapter content."""
    # Extract key points for SOP based on chapter
    sop_items = {
        1: [
            ('✅', '评估客户肩关节活动度，特别是肩屈角度和內旋能力'),
            ('✅', '高位下拉前确认肩胛骨后倾与下沉能力'),
            ('✅', '起始握距约1.5倍肩宽，前臂垂直于地面'),
            ('✅', '口令引导"胸椎上抬→肱骨向下拉"而非"手拉"'),
            ('✅', '直臂下压时保持肘关节微屈（15-20°），避免过伸锁死'),
            ('✅', '离心阶段控制2-3秒回放，观察肩胛是否过早升起'),
            ('❌', '避免过度后仰借力——提示客户保持躯干稳定'),
            ('❌', '避免肩胛骨过度上提——提示"远离耳朵"'),
            ('⚠️', '存在肩峰下疼痛弧者，先转介评估再安排下拉类训练'),
            ('⚠️', '胸小肌紧张导致肩胛前倾者，优先处理肩胛控制再加载'),
        ],
        2: [
            ('✅', '悬挂起始位评估握力耐受和肩关节被动稳定'),
            ('✅', '退阶从弹力带辅助或离心控制开始'),
            ('✅', '向心期关注肩胛下沉→肘部向下向后的运动模式'),
            ('✅', '离心阶段3-5秒控制下放，避免自由落体'),
            ('✅', '握法选择：中立握对肩部最友好，正手次之'),
            ('❌', '禁止Kipping动作未经充分基础训练直接进行'),
            ('❌', '避免过度耸肩——肩胛上提代偿提示负荷超出能力'),
            ('⚠️', '体重与力量比是引体向上的核心限制因素'),
            ('⚠️', '速度衰减超过20%时应停止该组训练'),
        ],
        3: [
            ('✅', '髋铰链起始位置建立：髋后移、脊柱中立、胫骨垂直'),
            ('✅', '划船发力关注"肘部向后上方引导"而非手握'),
            ('✅', '胸椎段有症状时，降低负荷或改为支撑划船'),
            ('✅', '正手划船更多招募上背与后三角，反手更多肱二头肌'),
            ('✅', '单侧划船需关注骨盆额状面稳定'),
            ('❌', '避免腰椎过度伸展代偿——提示"收腹维持中立"'),
            ('❌', '避免肩胛骨过度后缩导致肩关节挤压'),
            ('⚠️', '胸椎活动度不足者先改善活动度再增加划船负荷'),
        ],
        4: [
            ('✅', '绳索高度设置在头侧略上方'),
            ('✅', '选用绳索握把，末端朝面部方向'),
            ('✅', '动作终点关注肩胛后缩+肩外旋的复合动作'),
            ('✅', '离心阶段控制3秒，感受后三角与中下斜方肌'),
            ('✅', '作为肩关节健康的预防性练习安排'),
            ('❌', '避免过度耸肩——面拉的目标肌群是后链而非上斜方'),
            ('❌', '避免躯干过度后仰借力'),
            ('⚠️', '肩关节前方不适者，减小外旋幅度并降低负荷'),
        ],
        5: [
            ('✅', '评估肩屈活动度≥170°方可进行完整过头推举'),
            ('✅', '起始位杠铃/哑铃位于前 rack 位或肩侧'),
            ('✅', '发力时关注"头顶上方汇合"而非"向前推"'),
            ('✅', '站姿肩推需关注核心刚性与骨盆位置'),
            ('✅', '坐姿肩推减少下肢代偿，适合初学者'),
            ('❌', '避免腰椎过度前凸代偿——提示"肋骨下沉"'),
            ('❌', '避免头部过度前探让过杠铃'),
            ('⚠️', '肩峰下撞击症状者评估肩胛运动学后再决定动作选择'),
        ],
        6: [
            ('✅', '卧推前检查五个关键支撑点：头/上背/臀/双脚/杠铃'),
            ('✅', '握距确认：前臂在最低点垂直于地面'),
            ('✅', '肩胛骨后缩下沉，建立稳定的胸椎支撑'),
            ('✅', '手腕保持中立位，杠铃位于掌根正上方'),
            ('✅', '杠铃轨迹：从乳头线下放到胸骨，向心期略向面部方向'),
            ('❌', '避免起桥过高导致腰椎剪切力过大'),
            ('❌', '避免杠铃弹胸——控制触胸后短暂停顿再起'),
            ('⚠️', '肩关节活动度不足者先评估再确定握距'),
            ('⚠️', '无保护者训练时不使用大重量或力竭策略'),
        ],
        7: [
            ('✅', '评估踝关节背屈活动度：膝触墙测试≥10cm'),
            ('✅', '分腿蹲前确认骨盆额状面稳定能力'),
            ('✅', '前腿关注"髋→膝→踝"依次屈曲的运动序列'),
            ('✅', '后腿关注髋关节伸展控制，非过度膝关节屈曲'),
            ('✅', '足底三点支撑：大脚趾球、小脚趾球、脚跟'),
            ('❌', '避免前膝过度内扣——观察并提示"膝盖追第二趾"'),
            ('❌', '避免躯干过度前倾——提示"胸部保持朝前"'),
            ('⚠️', '跟腱/髌腱症状者先做等长负荷测试再决定训练强度'),
        ],
        8: [
            ('✅', '评估踝关节背屈活动度，不足者先改善'),
            ('✅', '站距与站姿个体化：根据髋关节解剖调整'),
            ('✅', '下蹲深度因人而异，以症状和动作为指导'),
            ('✅', '关注膝关节追踪方向与足部方向一致'),
            ('✅', '高杠位适合初学者，前蹲适合躯干直立需求者'),
            ('❌', '避免膝关节内扣不加控制'),
            ('❌', '避免因追求深度而牺牲腰椎中立'),
            ('⚠️', 'ACL/PCL损伤史者需专科评估后制定训练方案'),
            ('⚠️', '髌股疼痛者优先做负荷管理，非完全禁练'),
        ],
        9: [
            ('✅', '平板支撑前评估肩胛稳定能力——翼状肩胛者先做前锯肌激活'),
            ('✅', '平板支撑关注"肩胛前伸+腹部收紧"而非单纯撑住'),
            ('✅', '俯卧撑关注肩胛骨的运动节律——下落时后缩，推起时前伸'),
            ('✅', '俯卧撑退阶从墙壁→台面→跪姿→标准逐步推进'),
            ('✅', '前锯肌激活：推墙练习或仰卧前锯拳'),
            ('❌', '避免平板支撑时腰部塌陷——提示"尾骨微卷"'),
            ('❌', '避免俯卧撑时肩胛骨固定不动'),
            ('⚠️', '腕关节疼痛者可改用俯卧撑架或哑铃支撑'),
        ],
        10: [
            ('✅', '弯举时上臂紧贴体侧，避免前后移动产生肩部代偿'),
            ('✅', '锤式弯举可同时训练肱肌与前臂肌群'),
            ('✅', '三头肌过头位训练可最大化长头拉伸与募集'),
            ('✅', '侧平举在肩胛平面（前屈约30°）执行最符合关节力学'),
            ('✅', '三角肌训练容量分配：后束≥中束≥前束'),
            ('❌', '避免弯举中的躯干摆动借力'),
            ('❌', '避免侧平举时肩带上抬代偿'),
            ('⚠️', '前束训练在推类复合动作中已充分刺激，孤立训练边际收益有限'),
        ],
    }
    
    items = sop_items.get(ch_num, [])
    rows = []
    for i, (icon, label) in enumerate(items, 1):
        rows.append(f'''<div class="sop-row"><span class="sop-num">{icon}</span><span class="sop-label">{html_esc(label)}</span></div>''')
    
    return '\n'.join(rows)


def generate_flashcards(ch_num):
    """Generate flashcard HTML for a chapter."""
    cards = {
        1: [
            ('背阔肌四段式解剖模型包括哪四个区域？', '①肱骨止点与腋后壁 ②肩胛下角变异附着 ③胸腰筋膜联系 ④髂嵴及腰骶筋膜联系'),
            ('背阔肌在肩关节的三个主要动作是什么？', '内收（adduction）、伸展（extension）、内旋（internal rotation）'),
            ('口令"肩胛远离耳朵"针对的是什么问题？', '肩胛骨上提代偿——背阔肌/大圆肌发力不足时上斜方肌过度参与'),
            ('高位下拉中下斜方肌的作用是什么？', '肩胛骨后倾（posterior tilt）与下沉控制，背阔肌主要作用于肱骨而非肩胛'),
            ('背阔肌与肩关节稳定性的"双面关系"指什么？', '背阔肌产生内旋力矩参与前方稳定，但过度紧张可限制肩屈和外旋活动度'),
            ('大圆肌与背阔肌的关系是什么？', '两者共同构成腋后襞，存在不同形式的结构联系（Dancker 2017），但静态解剖联系不能证明训练时必定同步激活'),
            ('高位下拉握距的建议是什么？', '约1.5倍肩宽，前臂在最低点垂直于地面；过宽减少ROM，过窄增加肘部负荷'),
            ('等长下拉对肩峰肱骨间距有何影响？', '适度等长收缩可增加肩峰下间隙，但过度用力可能减小间隙空间'),
            ('直臂下压主要训练背阔肌的什么功能？', '肩关节伸展（shoulder extension），纤维从肱骨向躯干方向拉'),
            ('高位下拉的驼背姿势对训练有什么影响？', '驼背可减少肩胛后缩幅度，影响下斜方肌参与，但也可能降低肩峰下撞击风险'),
        ],
        2: [
            ('引体向上的力学分期包括哪几个阶段？', '悬挂准备→肩胛激活（scapular setting）→向心拉起→顶端控制→离心回放'),
            ('引体向上的三个主要发力肌群是什么？', '背阔肌（肩内收/伸展）、肱二头肌/肱肌（肘屈曲）、下斜方肌/菱形肌（肩胛后缩下沉）'),
            ('速度衰减作为训练停止指标的含义是什么？', '当连续重复动作中速度下降超过20%时，神经肌肉疲劳显著，应停止该组'),
            ('毛巾握引体向上与标准握的区别是什么？', '毛巾握大幅增加前臂和握力需求，但可能降低背阔肌激活程度'),
            ('Kipping引体向上的生物力学风险是什么？', '利用动量减少肌肉负荷但大幅增加肩关节囊和韧带的剪切力，肩关节稳定性不足者风险高'),
            ('不同握法对肩部运动学的影响是什么？', '正手（pronated）肩关节外旋更多；中立握（neutral）对肩关节最友好；反手（supinated）肱二头肌激活更多'),
            ('引体向上退阶训练的首选方式是什么？', '离心控制（eccentric focus）或弹力带辅助，而非辅助引体器械'),
            ('体重与力量比对引体向上的影响是什么？', '引体向上本质是相对力量测试；体重增加1kg约需额外产生对应力矩，力量训练与体重管理需同步'),
        ],
        3: [
            ('划船动作中斜方肌的主要功能分区是什么？', '上束：肩胛上提；中束：肩胛后缩；下束：肩胛下沉与后倾'),
            ('划船中"肩胛骨预收"的实际效果是什么？', '研究显示预收可增加中下斜方肌激活，但对背阔肌激活无显著差异；不应过度强调'),
            ('正手与反手划船的主要差异是什么？', '正手（pronated）更多上背与后三角肌激活；反手（supinated）更多肱二头肌参与'),
            ('划船中髋铰链起始位置的关键是什么？', '髋后移、脊柱中立、胫骨近似垂直、重心在足中'),
            ('单侧划船相比双侧的优势是什么？', '减少腰椎负荷需求，允许更大的单侧肩关节活动范围，纠正左右不对称'),
            ('胸椎段症状时的划船调整策略是什么？', '降低负荷→改为支撑划船→减少ROM→若症状持续则转介评估'),
            ('划船与弯举在训练中的关系是什么？', '弯举主要训练肱二头肌，划船训练背部肌群；弯举可作为背部训练容量的补充而非替代'),
        ],
        4: [
            ('面拉的主要目标肌群是什么？', '后三角肌、中下斜方肌、菱形肌——肩胛后缩+肩外旋的复合动作'),
            ('面拉绳索高度设置建议是什么？', '头侧略上方，使绳索从面部两侧经过'),
            ('面拉为什么被称为"肩胛平面的后链整合"？', '它同时训练肩胛后缩（中斜方/菱形肌）、肩外旋（后三角/冈下肌/小圆肌）和肩胛后倾（下斜方肌）'),
            ('面拉的推荐训练容量是多少？', '通常3组×12-15次，低负荷高次数，作为预防性练习而非主训练'),
            ('面拉与反向飞鸟的主要区别是什么？', '面拉包含肩外旋成分，更多后链整合；反向飞鸟主要是水平面的肩胛后缩'),
            ('面拉在训练计划中的定位是什么？', '热身激活（2-3组轻重量）或主训练后的辅助练习'),
            ('面拉对肩关节健康有什么预防意义？', '强化肩胛后缩肌群和肩外旋肌群，对抗推类动作造成的前侧优势模式'),
        ],
        5: [
            ('肩推的动力链整合指的是什么？', '从足底→核心→肩带→手臂的力传递链，不是孤立肩部发力'),
            ('肩推前评估肩屈活动度的标准是什么？', '≥170°方可进行完整过头推举；不足者先改善活动度或改为Landmine推举'),
            ('站姿与坐姿肩推的主要区别是什么？', '站姿需要更多核心稳定和下肢力量传递；坐姿减少下肢代偿，更适合孤立肩部训练'),
            ('肩推中腰椎过度前凸代偿的原因是什么？', '肩屈活动度不足或核心刚性不足，导致腰椎超伸补偿'),
            ('肩推的杠铃轨迹应该是什么？', '略呈弧线，从锁骨/前肩位向头顶上方略偏后方推送'),
            ('半跪姿肩推的训练价值是什么？', '减少下肢稳定需求，聚焦肩带控制与核心抗伸展能力'),
            ('肩推中"肋骨下沉"口令的目的？', '防止腰椎过度伸展代偿，维持核心刚性'),
        ],
        6: [
            ('卧推的五个关键支撑点是什么？', '头部、上背/肩胛骨、臀部、双脚、杠铃——五点是卧推安全的基础'),
            ('卧推握距如何确定？', '前臂在最低点（杠铃触胸时）垂直于地面；通常约1.5倍肩距'),
            ('肩胛骨后缩在卧推中的作用是什么？', '建立稳定的胸椎支撑平台，缩短杠铃行程，减少肩关节前侧压力'),
            ('腰椎起桥的讨论结论是什么？', '适度起桥可增加稳定性和力量传递，但过度起桥显著增加腰椎剪切力'),
            ('卧推的保护原则包括哪些？', '有保护者或安全销设置；不用弹胸；控制离心；力竭时有退出策略'),
            ('卧推中手腕应保持什么位置？', '中立位，杠铃位于掌根正上方，避免过度伸展'),
            ('卧推杠铃轨迹是什么？', '下放至胸骨中下段（约乳头线），向心期略向面部方向移动'),
            ('卧推中肘部角度的注意事项？', '前臂在底部垂直于地面，避免肘部过度外展（<80°）减少肩关节压力'),
        ],
        7: [
            ('分腿蹲中臀中肌的主要功能是什么？', '骨盆额状面稳定——防止摆动腿侧骨盆下沉（Trendelenburg征）'),
            ('阔筋膜张肌与髂胫束的关系是什么？', 'TFL是IT band的主要张力来源之一；紧张时可能增加膝外侧压力'),
            ('分腿蹲前腿的主要发力肌群是什么？', '股四头肌（膝伸展）、臀大肌（髋伸展）、臀中肌（骨盆稳定）'),
            ('分腿蹲中肌腱能量传递的含义是什么？', '前腿的肌腱系统在离心-向心转换中储存和释放弹性能量，类似弹簧机制'),
            ('足底三点支撑指的是什么？', '大脚趾球、小脚趾球、脚跟——三点形成稳定三角'),
            ('分腿蹲后腿的训练目标是什么？', '髋关节伸展控制与膝关节稳定，非单纯"后腿伸直"'),
            ('膝关节内扣的纠正策略是什么？', '降低负荷→提示"膝盖追第二趾"→加强臀中肌激活→评估足弓控制'),
            ('推雪橇作为深蹲替代训练的优势是什么？', '减少离心负荷对关节的冲击，同时维持股四头肌训练刺激，适合关节症状者'),
        ],
        8: [
            ('深蹲时髌股关节的受力特征是什么？', '膝关节屈曲角度越大，髌股关节压缩力越大；但适当深度可增强股四头肌力量'),
            ('前蹲与后蹲的主要力学差异是什么？', '前蹲躯干更直立→膝关节屈曲更大→股四头肌需求更高→腰椎负荷更低'),
            ('高杠与低杠背蹲的区别是什么？', '高杠：杠铃在C7附近，躯干更直立，膝关节屈曲更大；低杠：杠铃在三角肌后束，躯干前倾更多，髋关节需求更高'),
            ('踝关节背屈不足对深蹲的影响？', '导致躯干过度前倾或脚跟抬起，影响整体力学和稳定性'),
            ('膝关节内扣（knee valgus）的机制是什么？', '股骨内旋+内收，与臀中肌控制不足、足弓塌陷、踝背屈受限相关'),
            ('深蹲深度与损伤风险的关系是什么？', '适当深度不增加损伤风险；浅蹲膝关节剪切力更小但股四头肌刺激有限；深蹲需足够活动度支撑'),
            ('推雪橇为什么可作为深蹲替代？', '几乎没有离心负荷，大幅减少关节压缩力和肌肉损伤，同时提供股四头肌训练刺激'),
            ('ACL损伤史者的深蹲策略是什么？', '专科评估→控制ROM→避免剪切力大的位置→渐进负荷→关注神经肌肉控制训练'),
        ],
        9: [
            ('平板支撑涉及的核心肌群有哪些？', '腹直肌、腹横肌、腹内外斜肌、多裂肌、竖脊肌——等长抗伸展收缩'),
            ('翼状肩胛的临床意义是什么？', '前锯肌功能障碍的标志；影响肩胛骨贴附胸壁的能力，限制过头动作'),
            ('俯卧撑的力学结构特点是什么？', '闭链运动，肩胛骨可自由运动，训练肩胛稳定肌和前锯肌'),
            ('平板支撑的耐力与运动表现的关联是什么？', '平板支撑耐力≥120秒与较低的腰痛风险相关（McGill），但不代表训练效果的最优指标'),
            ('俯卧撑与低负荷卧推的训练比较结论？', '低负荷俯卧撑可达到类似的胸肌和三角肌激活水平，且额外训练肩胛稳定'),
            ('前锯肌激活的最佳方法是什么？', '推墙练习（wall push-up plus）或仰卧前锯拳；研究显示加号动作（plus）显著增加前锯肌激活'),
            ('俯卧撑退阶路径是什么？', '墙壁→台面→跪姿→标准俯卧撑'),
            ('平板支撑进阶路径是什么？', '标准→手肘交替支撑→负重→不稳定平面（如Bosu球）→单臂/单腿变式'),
        ],
        10: [
            ('肱二头肌的两个头分别起自哪里？', '长头：肩胛骨盂上结节（经关节囊内）；短头：喙突'),
            ('弯举中上臂位置对肌肉激活的影响？', '上臂后伸（如incline curl）增加长头拉伸和激活；上臂前屈（如spider curl）短头优势'),
            ('拉长位训练的肥大效应证据？', 'Pedrosa et al.(2022)等研究显示，肌肉拉长位训练（如incline curl）比缩短位产生更大的肱二头肌肥大'),
            ('三头肌长头为什么需要过头位训练？', '长头跨越肩关节，过头位（overhead position）可充分拉伸长头，研究显示显著增加长头肥大'),
            ('侧平举的力学特征是什么？', '阻力曲线呈钟形：30-60°力矩最大，0°和90°力矩最小；应在肩胛平面执行'),
            ('三角肌后束的面拉vs反向飞鸟比较？', '面拉包含肩外旋成分，更全面激活后链；反向飞鸟主要是水平面后缩'),
            ('三角肌前束是否需要孤立训练？', '推类复合动作（卧推、肩推）已充分刺激前束，孤立训练边际收益有限'),
            ('弯举中的前臂旋后控制的意义？', '旋后（supination）可最大化肱二头肌激活，因为肱二头肌同时是前臂旋后肌'),
            ('三角肌训练容量分配建议？', '后束≥中束≥前束——后束训练量不足是最常见问题'),
        ],
    }
    
    card_list = cards.get(ch_num, [])
    html_parts = []
    for i, (q, a) in enumerate(card_list):
        html_parts.append(f'''<div class="flashcard" onclick="this.classList.toggle('flipped')">
  <div class="flashcard-inner">
    <div class="flashcard-front">
      <div class="flashcard-label">Card {i+1}</div>
      <div class="flashcard-text">{html_esc(q)}</div>
    </div>
    <div class="flashcard-back">
      <div class="flashcard-label">Answer</div>
      <div class="flashcard-text">{html_esc(a)}</div>
    </div>
  </div>
</div>''')
    return '\n'.join(html_parts)


def generate_quiz(ch_num):
    """Generate quiz HTML for a chapter."""
    quizzes = {
        1: [
            {
                'q': '背阔肌在肩关节的主要动作不包括以下哪项？',
                'opts': ['肩关节内收', '肩关节伸展', '肩关节外展', '肩关节内旋'],
                'ans': 2,
                'exp': '背阔肌产生内收、伸展和内旋力矩，不产生外展。外展由三角肌中束和冈上肌主导。'
            },
            {
                'q': '关于背阔肌四段式解剖模型，以下哪项描述正确？',
                'opts': ['四段结构由肱骨经肩胛骨串联至骨盆', '这是教学用的区域地图，不是四块独立肌肉', '每段独立产生不同的关节力矩', '所有区域的纤维走向完全一致'],
                'ans': 1,
                'exp': '四段式解剖模型是教学用的区域地图，不是四块独立肌肉，也不是串联结构。'
            },
            {
                'q': '大圆肌与背阔肌的解剖研究（Dancker 2017）表明什么？',
                'opts': ['训练时两肌必定同步激活', '两者存在不同形式的结构联系', '背阔肌可以被完全孤立训练', '大圆肌是背阔肌的协同肌而非独立肌'],
                'ans': 1,
                'exp': '解剖研究提示两者存在不同形式的结构联系，但静态解剖不能证明训练时必定同步激活。'
            },
            {
                'q': '高位下拉中下斜方肌的主要功能是什么？',
                'opts': ['肩关节内收', '肩胛骨后倾与下沉控制', '肩关节伸展', '肘关节屈曲辅助'],
                'ans': 1,
                'exp': '下斜方肌参与肩胛骨后倾（posterior tilt）和下沉控制，背阔肌主要作用于肱骨。'
            },
            {
                'q': '关于等长下拉与肩峰肱骨间距，以下哪项正确？',
                'opts': ['等长收缩总是减小肩峰下间隙', '适度等长收缩可增加肩峰下间隙', '等长收缩对肩峰下间隙无影响', '仅离心收缩影响肩峰下间隙'],
                'ans': 1,
                'exp': '适度等长收缩可增加肩峰下间隙，但过度用力可能减小间隙空间。'
            },
            {
                'q': '直臂下压主要训练的肩关节动作是什么？',
                'opts': ['肩关节内收', '肩关节伸展', '肩关节内旋', '肩关节外展'],
                'ans': 1,
                'exp': '直臂下压主要训练肩关节伸展功能，纤维从肱骨向躯干方向拉。'
            },
        ],
        2: [
            {
                'q': '引体向上的力学分期中，肩胛激活（scapular setting）位于哪个阶段？',
                'opts': ['悬挂准备之前', '悬挂准备之后、向心拉起之前', '向心拉起与顶端控制之间', '离心回放之后'],
                'ans': 1,
                'exp': '肩胛激活在悬挂准备之后、向心拉起之前，是建立稳定发力的关键环节。'
            },
            {
                'q': '速度衰减作为训练停止指标的标准是什么？',
                'opts': ['速度下降10%', '速度下降15%', '速度下降20%', '速度下降30%'],
                'ans': 2,
                'exp': '当连续重复动作中速度下降超过20%时，神经肌肉疲劳显著，应停止该组训练。'
            },
            {
                'q': '以下哪种握法对肩关节最友好？',
                'opts': ['正手宽握（pronated wide）', '中立握（neutral）', '反手窄握（supinated narrow）', '毛巾握（towel grip）'],
                'ans': 1,
                'exp': '中立握对肩关节最友好，正手次之，毛巾握增加前臂和握力需求。'
            },
            {
                'q': 'Kipping引体向上的主要生物力学风险是什么？',
                'opts': ['减少肌肉训练效果', '大幅增加肩关节囊和韧带的剪切力', '增加肘关节内翻应力', '导致腰椎过度伸展'],
                'ans': 1,
                'exp': 'Kipping利用动量减少肌肉负荷但大幅增加肩关节囊和韧带的剪切力。'
            },
            {
                'q': '引体向上退阶训练的首选方式是什么？',
                'opts': ['辅助引体器械', '离心控制', '弹力带辅助', '跳起引体'],
                'ans': 1,
                'exp': '离心控制（eccentric focus）或弹力带辅助是退阶首选，优于辅助引体器械。'
            },
        ],
        3: [
            {
                'q': '划船中"肩胛骨预收"的研究结论是什么？',
                'opts': ['显著增加背阔肌激活', '可增加中下斜方肌激活但对背阔肌无显著差异', '对任何肌肉激活均无影响', '增加肩关节前侧压力'],
                'ans': 1,
                'exp': '研究显示预收可增加中下斜方肌激活，但对背阔肌激活无显著差异。'
            },
            {
                'q': '正手划船相比反手划船更多地激活哪个区域？',
                'opts': ['肱二头肌', '上背与后三角肌', '前锯肌', '胸大肌'],
                'ans': 1,
                'exp': '正手（pronated）划船更多上背与后三角肌激活；反手更多肱二头肌参与。'
            },
            {
                'q': '单侧划船相比双侧划船的优势是什么？',
                'opts': ['训练时间减半', '减少腰椎负荷需求并纠正左右不对称', '增加总负荷能力', '消除所有代偿'],
                'ans': 1,
                'exp': '单侧划船减少腰椎负荷需求，允许更大的单侧肩关节活动范围，纠正不对称。'
            },
            {
                'q': '胸椎段有症状时的划船调整优先级是什么？',
                'opts': ['立即停止所有训练', '降低负荷→改为支撑划船→减少ROM→转介', '直接换为下拉动作', '增加热身组数'],
                'ans': 1,
                'exp': '按渐进策略调整：降低负荷→改为支撑划船→减少ROM→若症状持续则转介评估。'
            },
            {
                'q': '划船中髋铰链起始位置的关键要素不包括？',
                'opts': ['髋后移', '脊柱中立', '膝关节完全伸直', '重心在足中'],
                'ans': 2,
                'exp': '髋铰链要求胫骨近似垂直（膝关节微屈），非完全伸直。'
            },
        ],
        4: [
            {
                'q': '面拉的主要目标肌群组合是什么？',
                'opts': ['上斜方肌和三角肌前束', '后三角肌、中下斜方肌和菱形肌', '背阔肌和肱二头肌', '胸大肌和前锯肌'],
                'ans': 1,
                'exp': '面拉同时训练后三角肌、中下斜方肌、菱形肌——肩胛后缩+肩外旋的复合动作。'
            },
            {
                'q': '面拉推荐的训练参数是什么？',
                'opts': ['5组×5次大重量', '3组×12-15次低负荷', '2组×30次极轻负荷', '1组×力竭'],
                'ans': 1,
                'exp': '通常3组×12-15次，低负荷高次数，作为预防性练习而非主训练。'
            },
            {
                'q': '面拉与反向飞鸟的关键区别是什么？',
                'opts': ['目标肌群完全不同', '面拉包含肩外旋成分，更多后链整合', '反向飞鸟更多后三角肌激活', '两者没有实质区别'],
                'ans': 1,
                'exp': '面拉包含肩外旋成分，更全面激活后链；反向飞鸟主要是水平面的肩胛后缩。'
            },
            {
                'q': '面拉对肩关节健康的预防意义是什么？',
                'opts': ['增加肩关节灵活性', '强化肩胛后缩肌群和肩外旋肌群，对抗推类动作的前侧优势', '直接治疗肩关节损伤', '替代所有肩部训练'],
                'ans': 1,
                'exp': '面拉强化肩胛后缩肌群和肩外旋肌群，对抗推类动作造成的前侧优势模式。'
            },
            {
                'q': '面拉绳索高度应设置在什么位置？',
                'opts': ['胸部高度', '腰部高度', '头侧略上方', '正上方'],
                'ans': 2,
                'exp': '绳索高度设置在头侧略上方，使绳索从面部两侧经过。'
            },
        ],
        5: [
            {
                'q': '肩推前评估肩屈活动度的标准是什么？',
                'opts': ['≥150°', '≥160°', '≥170°', '≥180°'],
                'ans': 2,
                'exp': '肩屈活动度≥170°方可进行完整过头推举。'
            },
            {
                'q': '站姿与坐姿肩推的主要区别是什么？',
                'opts': ['站推更多肩部肌肉激活', '坐姿减少下肢代偿适合初学者', '站推对肩关节更安全', '两者没有实质区别'],
                'ans': 1,
                'exp': '站姿需要更多核心稳定和下肢力量传递；坐姿减少下肢代偿，更适合初学者。'
            },
            {
                'q': '肩推中"肋骨下沉"口令的目的是什么？',
                'opts': ['增加胸椎灵活性', '防止腰椎过度伸展代偿，维持核心刚性', '增加腹直肌训练效果', '改善呼吸模式'],
                'ans': 1,
                'exp': '防止腰椎过度伸展代偿，维持核心刚性。'
            },
            {
                'q': '肩推中腰椎过度前凸代偿的常见原因是什么？',
                'opts': ['负荷过轻', '肩屈活动度不足或核心刚性不足', '站距过宽', '握距过窄'],
                'ans': 1,
                'exp': '肩屈活动度不足或核心刚性不足，导致腰椎超伸补偿。'
            },
            {
                'q': '半跪姿肩推的训练价值是什么？',
                'opts': ['最大化肩部力量', '减少下肢稳定需求，聚焦肩带控制与核心抗伸展', '增加腰椎负荷', '减少肩关节活动范围'],
                'ans': 1,
                'exp': '半跪姿减少下肢稳定需求，聚焦肩带控制与核心抗伸展能力。'
            },
        ],
        6: [
            {
                'q': '卧推的五个关键支撑点不包括以下哪项？',
                'opts': ['头部', '肩胛骨/上背', '膝关节', '杠铃'],
                'ans': 2,
                'exp': '五点是：头部、上背/肩胛骨、臀部、双脚、杠铃。膝关节不是支撑点。'
            },
            {
                'q': '卧推中肩胛骨后缩的主要作用是什么？',
                'opts': ['增加杠铃行程', '建立稳定的胸椎支撑平台并减少肩关节前侧压力', '增加肱三头肌激活', '减少腰椎负荷'],
                'ans': 1,
                'exp': '肩胛骨后缩建立稳定的胸椎支撑平台，缩短杠铃行程，减少肩关节前侧压力。'
            },
            {
                'q': '关于腰椎起桥的讨论，以下哪项正确？',
                'opts': ['起桥越大越安全', '完全禁止起桥', '适度起桥可增加稳定性但过度起桥增加腰椎剪切力', '起桥对力学无影响'],
                'ans': 2,
                'exp': '适度起桥可增加稳定性和力量传递，但过度起桥显著增加腰椎剪切力。'
            },
            {
                'q': '卧推中手腕应保持什么位置？',
                'opts': ['完全伸直', '中立位，杠铃位于掌根正上方', '尺侧偏斜', '桡侧偏斜'],
                'ans': 1,
                'exp': '手腕保持中立位，杠铃位于掌根正上方，避免过度伸展。'
            },
            {
                'q': '卧推杠铃的运动轨迹是什么？',
                'opts': ['完全垂直上下', '略呈弧线，下放至胸骨中下段，向心期略向面部方向', '从胸部向头部方向移动', '水平前后移动'],
                'ans': 1,
                'exp': '杠铃轨迹略呈弧线，下放至胸骨中下段（约乳头线），向心期略向面部方向。'
            },
        ],
        7: [
            {
                'q': '分腿蹲中臀中肌的主要功能是什么？',
                'opts': ['髋关节伸展', '骨盆额状面稳定', '膝关节伸展', '踝关节背屈'],
                'ans': 1,
                'exp': '臀中肌在分腿蹲中的主要功能是骨盆额状面稳定——防止摆动腿侧骨盆下沉。'
            },
            {
                'q': '足底三点支撑包括哪三个点？',
                'opts': ['脚趾尖、足弓中心、脚跟', '大脚趾球、小脚趾球、脚跟', '大脚趾、小脚趾、足弓', '前掌、中足、后跟'],
                'ans': 1,
                'exp': '足底三点支撑：大脚趾球、小脚趾球、脚跟，形成稳定三角。'
            },
            {
                'q': '膝关节内扣（knee valgus）的纠正策略优先级是什么？',
                'opts': ['增加负荷→强化训练', '降低负荷→提示"膝盖追第二趾"→加强臀中肌→评估足弓', '使用护膝', '完全停止训练'],
                'ans': 1,
                'exp': '纠正策略：降低负荷→提示"膝盖追第二趾"→加强臀中肌激活→评估足弓控制。'
            },
            {
                'q': '分腿蹲中肌腱能量传递的含义是什么？',
                'opts': ['肌肉主动收缩产生的力', '肌腱在离心-向心转换中储存和释放弹性能量', '韧带对关节的保护', '神经信号传递'],
                'ans': 1,
                'exp': '肌腱系统在离心-向心转换中储存和释放弹性能量，类似弹簧机制。'
            },
            {
                'q': '推雪橇作为深蹲替代训练的优势是什么？',
                'opts': ['增加最大力量', '减少离心负荷对关节的冲击同时维持股四头肌刺激', '增加髋关节活动度', '改善平衡能力'],
                'ans': 1,
                'exp': '推雪橇减少离心负荷对关节的冲击，同时维持股四头肌训练刺激。'
            },
        ],
        8: [
            {
                'q': '前蹲与后蹲的主要力学差异是什么？',
                'opts': ['前蹲腰椎负荷更大', '前蹲躯干更直立，膝关节屈曲更大，股四头肌需求更高', '后蹲更适合初学者', '两者力学完全相同'],
                'ans': 1,
                'exp': '前蹲躯干更直立→膝关节屈曲更大→股四头肌需求更高→腰椎负荷更低。'
            },
            {
                'q': '高杠与低杠背蹲的关键区别是什么？',
                'opts': ['高杠腰椎负荷更大', '低杠杠铃在C7附近', '高杠躯干更直立膝关节屈曲更大；低杠躯干前倾更多髋关节需求更高', '两者对肌肉激活无差异'],
                'ans': 2,
                'exp': '高杠：杠铃在C7附近，躯干更直立，膝关节屈曲更大；低杠：杠铃在三角肌后束，躯干前倾更多，髋关节需求更高。'
            },
            {
                'q': '膝关节内扣（knee valgus）的主要机制是什么？',
                'opts': ['股骨外旋+外展', '股骨内旋+内收', '胫骨外旋', '踝关节内翻'],
                'ans': 1,
                'exp': '膝关节内扣的机制是股骨内旋+内收，与臀中肌控制不足、足弓塌陷、踝背屈受限相关。'
            },
            {
                'q': '关于深蹲深度与损伤风险，以下哪项正确？',
                'opts': ['深蹲越深损伤风险越大', '浅蹲完全没有损伤风险', '适当深度不增加损伤风险，深蹲需足够活动度支撑', '深度与损伤无关'],
                'ans': 2,
                'exp': '适当深度不增加损伤风险；浅蹲膝关节剪切力更小但股四头肌刺激有限；深蹲需足够活动度支撑。'
            },
            {
                'q': '推雪橇作为深蹲替代的生物力学原理是什么？',
                'opts': ['增加离心负荷', '几乎没有离心负荷，减少关节压缩力和肌肉损伤', '完全模拟深蹲力学', '增加腰椎轴向负荷'],
                'ans': 1,
                'exp': '推雪橇几乎没有离心负荷，大幅减少关节压缩力和肌肉损伤，同时提供股四头肌训练刺激。'
            },
        ],
        9: [
            {
                'q': '平板支撑训练的核心肌群收缩类型是什么？',
                'opts': ['等张向心收缩', '等张离心收缩', '等长抗伸展收缩', '等速收缩'],
                'ans': 2,
                'exp': '平板支撑涉及的核心肌群（腹直肌、腹横肌、多裂肌等）进行等长抗伸展收缩。'
            },
            {
                'q': '翼状肩胛（winged scapula）主要提示哪块肌肉功能障碍？',
                'opts': ['斜方肌上束', '前锯肌', '菱形肌', '背阔肌'],
                'ans': 1,
                'exp': '翼状肩胛是前锯肌功能障碍的标志，影响肩胛骨贴附胸壁的能力。'
            },
            {
                'q': '俯卧撑中肩胛骨的正确运动节律是什么？',
                'opts': ['始终后缩', '始终前伸', '下落时后缩，推起时前伸', '保持不动'],
                'ans': 2,
                'exp': '俯卧撑关注肩胛骨的运动节律——下落时后缩，推起时前伸。'
            },
            {
                'q': '俯卧撑退阶路径的正确顺序是什么？',
                'opts': ['台面→墙壁→跪姿→标准', '墙壁→台面→跪姿→标准', '跪姿→墙壁→台面→标准', '标准→跪姿→台面→墙壁'],
                'ans': 1,
                'exp': '俯卧撑退阶路径：墙壁→台面→跪姿→标准俯卧撑。'
            },
            {
                'q': '平板支撑耐力的最低标准是多少秒与较低腰痛风险相关？',
                'opts': ['60秒', '90秒', '120秒', '150秒'],
                'ans': 2,
                'exp': '平板支撑耐力≥120秒与较低的腰痛风险相关（McGill研究）。'
            },
        ],
        10: [
            {
                'q': '肱二头肌长头的起点在哪里？',
                'opts': ['喙突', '盂下结节', '盂上结节（经关节囊内）', '肩峰'],
                'ans': 2,
                'exp': '肱二头肌长头起自肩胛骨盂上结节，经关节囊内走行。'
            },
            {
                'q': '拉长位训练（如incline curl）对肱二头肌的肥大效应如何？',
                'opts': ['与缩短位无差异', '产生更大的肱二头肌肥大', '肥大效果更差', '仅影响短头'],
                'ans': 1,
                'exp': '研究显示拉长位训练（如incline curl）比缩短位产生更大的肱二头肌肥大。'
            },
            {
                'q': '三头肌长头为什么需要过头位训练？',
                'opts': ['减少肘关节压力', '过头位可充分拉伸长头，显著增加长头肥大', '增加前臂激活', '改善肩关节灵活性'],
                'ans': 1,
                'exp': '长头跨越肩关节，过头位可充分拉伸长头，研究显示显著增加长头肥大。'
            },
            {
                'q': '侧平举应在什么平面执行最符合关节力学？',
                'opts': ['额状面（完全侧方）', '肩胛平面（前屈约30°）', '矢状面（正前方）', '水平面'],
                'ans': 1,
                'exp': '侧平举在肩胛平面（前屈约30°）执行最符合关节力学。'
            },
            {
                'q': '三角肌训练的容量分配建议是什么？',
                'opts': ['前束≥中束≥后束', '中束≥前束≥后束', '后束≥中束≥前束', '三束均等'],
                'ans': 2,
                'exp': '后束≥中束≥前束——后束训练量不足是最常见问题。'
            },
            {
                'q': '为什么三角肌前束通常不需要孤立训练？',
                'opts': ['前束无法被孤立训练', '推类复合动作（卧推、肩推）已充分刺激前束', '前束没有训练价值', '前束容易受伤'],
                'ans': 1,
                'exp': '推类复合动作已充分刺激前束，孤立训练边际收益有限。'
            },
            {
                'q': '弯举中前臂旋后（supination）的意义是什么？',
                'opts': ['减少腕关节压力', '最大化肱二头肌激活，因为肱二头肌同时是前臂旋后肌', '增加前臂肌肉肥大', '改善握力'],
                'ans': 1,
                'exp': '旋后可最大化肱二头肌激活，因为肱二头肌同时是前臂旋后肌。'
            },
        ],
    }
    
    quiz_list = quizzes.get(ch_num, [])
    html_parts = []
    for i, q in enumerate(quiz_list):
        opts_html = ''
        for j, opt in enumerate(q['opts']):
            opts_html += f'<div class="quiz-opt" data-correct="{"true" if j == q["ans"] else "false"}" onclick="selectOpt(this)">{html_esc(opt)}</div>\n'
        
        html_parts.append(f'''<div class="quiz-item" data-explanation="{html_esc(q['exp'])}">
  <div class="quiz-q">{i+1}. {html_esc(q['q'])}</div>
  <div class="quiz-options">
{opts_html}  </div>
  <div class="quiz-feedback" style="display:none;margin-top:12px;padding:12px;background:var(--bg-tertiary);border-radius:var(--radius-sm);font-size:0.82rem;color:var(--text-secondary);"></div>
  <button class="quiz-check" onclick="checkQuiz(this)" style="margin-top:12px;padding:8px 20px;font-family:var(--font-mono);font-size:0.72rem;letter-spacing:1px;text-transform:uppercase;color:var(--accent);background:var(--accent-dim);border:1px solid var(--border-hover);border-radius:var(--radius-sm);cursor:pointer;">检查答案</button>
</div>''')
    return '\n'.join(html_parts)


def build_chapter_html(ch_num, title_en, subtitle_zh, lecture_html, sop_html, flashcard_html, quiz_html):
    """Build complete chapter HTML file."""
    ch_str = f'{ch_num:02d}'
    
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ch{ch_str} · {html_esc(title_en)} · SBST</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700;800&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root {{
  --bg-primary: #0a0a0f;
  --bg-secondary: #1a1a24;
  --bg-tertiary: #2a2a3a;
  --accent: #00d4ff;
  --accent-dim: rgba(0, 212, 255, 0.15);
  --accent-glow: rgba(0, 212, 255, 0.4);
  --text-primary: #e0e0e0;
  --text-secondary: #a0a0b0;
  --text-muted: #606070;
  --border: rgba(255, 255, 255, 0.06);
  --border-hover: rgba(0, 212, 255, 0.3);
  --card-shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
  --glow-sm: 0 0 8px rgba(0, 212, 255, 0.2);
  --glow-md: 0 0 20px rgba(0, 212, 255, 0.15);
  --font-mono: 'JetBrains Mono', 'Fira Code', 'SF Mono', monospace;
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --radius: 12px;
  --radius-sm: 8px;
  --transition: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ font-size: 16px; scroll-behavior: smooth; }}
body {{
  font-family: var(--font-sans);
  background: var(--bg-primary);
  color: var(--text-primary);
  min-height: 100vh;
  overflow-x: hidden;
  line-height: 1.6;
}}
body::before {{
  content: '';
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px);
  background-size: 60px 60px;
  pointer-events: none;
  z-index: 0;
}}
.container {{ max-width: 960px; margin: 0 auto; padding: 0 24px; position: relative; z-index: 1; }}

/* ========== NAV ========== */
.top-nav {{
  padding: 16px 0;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  background: rgba(10, 10, 15, 0.92);
  backdrop-filter: blur(12px);
  z-index: 100;
}}
.top-nav .container {{ display: flex; align-items: center; justify-content: space-between; }}
.nav-left {{ display: flex; align-items: center; gap: 16px; }}
.nav-back {{
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--text-secondary);
  text-decoration: none;
  letter-spacing: 1px;
  text-transform: uppercase;
  transition: color var(--transition);
}}
.nav-back:hover {{ color: var(--accent); }}
.nav-divider {{ width: 1px; height: 16px; background: var(--border); }}
.nav-chapter-title {{
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text-primary);
  font-weight: 600;
  letter-spacing: 1px;
}}
.nav-right {{ display: flex; align-items: center; gap: 16px; }}
.nav-user {{
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--text-secondary);
  letter-spacing: 1px;
}}

/* ========== CHAPTER HEADER ========== */
.chapter-header {{
  padding: 48px 0 32px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 0;
}}
.ch-number {{
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--accent);
  letter-spacing: 3px;
  text-transform: uppercase;
  margin-bottom: 8px;
}}
.ch-title {{
  font-family: var(--font-mono);
  font-size: clamp(1.3rem, 3vw, 1.8rem);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
  line-height: 1.3;
}}
.ch-subtitle {{
  font-size: 0.9rem;
  color: var(--text-secondary);
  font-weight: 300;
}}

/* ========== TABS ========== */
.tab-bar {{
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 53px;
  background: rgba(10, 10, 15, 0.95);
  backdrop-filter: blur(12px);
  z-index: 90;
  overflow-x: auto;
}}
.tab-btn {{
  padding: 14px 24px;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  font-weight: 500;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--text-muted);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: all var(--transition);
  white-space: nowrap;
  position: relative;
}}
.tab-btn:hover {{ color: var(--text-secondary); }}
.tab-btn.active {{
  color: var(--accent);
  border-bottom-color: var(--accent);
}}
.tab-btn.active::after {{
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--accent);
  box-shadow: var(--glow-sm);
}}

/* ========== TAB CONTENT ========== */
.tab-content {{ display: none; padding: 40px 0 80px; }}
.tab-content.active {{ display: block; }}

/* ========== LECTURE STYLES ========== */
.lecture-h3 {{
  font-family: var(--font-mono);
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--accent);
  margin: 36px 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-hover);
}}
.lecture-h4 {{
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 28px 0 12px;
}}
.lecture-h5 {{
  font-family: var(--font-mono);
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 22px 0 10px;
}}
.lecture-p {{
  font-size: 0.9rem;
  color: var(--text-primary);
  line-height: 1.75;
  margin-bottom: 14px;
}}
.lecture-list {{
  margin: 12px 0 16px 0;
  padding: 0;
  list-style: none;
}}
.lecture-list li {{
  font-size: 0.88rem;
  color: var(--text-primary);
  line-height: 1.65;
  padding: 4px 0 4px 20px;
  position: relative;
}}
.lecture-list li::before {{
  content: '›';
  position: absolute;
  left: 4px;
  color: var(--accent);
  font-weight: 700;
}}
.lecture-olist {{
  margin: 12px 0 16px 0;
  padding: 0 0 0 20px;
  list-style: none;
  counter-reset: lecture-counter;
}}
.lecture-olist li {{
  font-size: 0.88rem;
  color: var(--text-primary);
  line-height: 1.65;
  padding: 4px 0 4px 28px;
  position: relative;
  counter-increment: lecture-counter;
}}
.lecture-olist li::before {{
  content: counter(lecture-counter) '.';
  position: absolute;
  left: 4px;
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 600;
}}
.lecture-blockquote {{
  margin: 16px 0;
  padding: 14px 20px;
  background: var(--bg-secondary);
  border-left: 3px solid var(--accent);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  font-style: italic;
  font-size: 0.85rem;
  color: var(--text-secondary);
  line-height: 1.6;
}}
.lecture-blockquote a {{
  color: var(--accent);
  text-decoration: underline;
}}
.lecture-table-wrap {{
  margin: 20px 0;
  overflow-x: auto;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
}}
.lecture-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}}
.lecture-table th {{
  background: var(--bg-tertiary);
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  padding: 12px 14px;
  text-align: left;
  border-bottom: 1px solid var(--border-hover);
}}
.lecture-table td {{
  padding: 10px 14px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}}
.lecture-table tr:last-child td {{ border-bottom: none; }}
.lecture-table tr:hover td {{ background: rgba(0, 212, 255, 0.02); }}

/* ========== FLASHCARDS ========== */
.flashcard-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  margin-top: 24px;
}}
.flashcard {{
  perspective: 1000px;
  height: 180px;
  cursor: pointer;
}}
.flashcard-inner {{
  position: relative;
  width: 100%;
  height: 100%;
  transition: transform 0.6s cubic-bezier(0.4, 0, 0.2, 1);
  transform-style: preserve-3d;
}}
.flashcard.flipped .flashcard-inner {{ transform: rotateY(180deg); }}
.flashcard-front, .flashcard-back {{
  position: absolute;
  inset: 0;
  backface-visibility: hidden;
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  text-align: center;
}}
.flashcard-front {{
  background: linear-gradient(145deg, var(--bg-tertiary), var(--bg-secondary));
  border: 1px solid var(--border-hover);
  box-shadow: inset 0 1px 0 rgba(0, 212, 255, 0.08);
}}
.flashcard-back {{
  background: linear-gradient(145deg, var(--bg-secondary), var(--bg-primary));
  border: 1px solid var(--accent);
  transform: rotateY(180deg);
  box-shadow: var(--glow-sm);
}}
.flashcard-label {{
  font-family: var(--font-mono);
  font-size: 0.6rem;
  color: var(--accent);
  letter-spacing: 2px;
  text-transform: uppercase;
  margin-bottom: 12px;
}}
.flashcard-text {{
  font-size: 0.88rem;
  color: var(--text-primary);
  line-height: 1.5;
}}
.flashcard-back .flashcard-text {{ color: var(--text-secondary); }}

/* ========== SOP TABLE ========== */
.sop-placeholder {{
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}}
.sop-row {{
  display: flex;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  align-items: center;
}}
.sop-row:last-child {{ border-bottom: none; }}
.sop-row:hover {{ background: rgba(0, 212, 255, 0.02); }}
.sop-num {{
  font-family: var(--font-mono);
  font-size: 0.85rem;
  width: 40px;
  flex-shrink: 0;
  text-align: center;
}}
.sop-label {{
  font-size: 0.85rem;
  color: var(--text-secondary);
  flex: 1;
}}

/* ========== QUIZ ========== */
.quiz-item {{
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  margin-bottom: 16px;
}}
.quiz-q {{
  font-family: var(--font-mono);
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 16px;
  line-height: 1.5;
}}
.quiz-options {{ display: flex; flex-direction: column; gap: 8px; }}
.quiz-opt {{
  padding: 12px 16px;
  font-size: 0.82rem;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition);
}}
.quiz-opt:hover {{ border-color: var(--border-hover); color: var(--text-primary); }}
.quiz-opt.selected {{ border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }}
.quiz-opt.correct {{ border-color: #4ade80; color: #4ade80; background: rgba(74, 222, 128, 0.1); }}
.quiz-opt.incorrect {{ border-color: #f87171; color: #f87171; background: rgba(248, 113, 113, 0.1); }}

/* ========== AI CHAT ========== */
.chat-fab {{
  position: fixed;
  bottom: 32px;
  right: 32px;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent), #00a0cc);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 20px rgba(0, 212, 255, 0.3);
  transition: all var(--transition);
  z-index: 1000;
}}
.chat-fab:hover {{ transform: scale(1.08); box-shadow: 0 6px 30px rgba(0, 212, 255, 0.45); }}
.chat-fab svg {{ width: 24px; height: 24px; fill: var(--bg-primary); }}

.chat-modal-overlay {{
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.7);
  backdrop-filter: blur(4px);
  z-index: 2000;
  display: none;
  align-items: center;
  justify-content: center;
}}
.chat-modal-overlay.active {{ display: flex; }}
.chat-modal {{
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 40px;
  max-width: 420px;
  width: 90%;
  text-align: center;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}}
.chat-modal-icon {{
  width: 48px; height: 48px;
  margin: 0 auto 20px;
  border-radius: 50%;
  background: var(--accent-dim);
  display: flex; align-items: center; justify-content: center;
}}
.chat-modal-icon svg {{ width: 24px; height: 24px; fill: var(--accent); }}
.chat-modal h3 {{ font-family: var(--font-mono); font-size: 1rem; font-weight: 600; margin-bottom: 8px; }}
.chat-modal p {{ font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 24px; }}
.chat-modal-close {{
  padding: 10px 28px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition);
}}
.chat-modal-close:hover {{ border-color: var(--accent); color: var(--accent); }}

/* ========== FOOTER ========== */
.site-footer {{
  padding: 32px 0;
  border-top: 1px solid var(--border);
  text-align: center;
}}
.footer-text {{
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: var(--text-muted);
  letter-spacing: 2px;
  text-transform: uppercase;
}}

@media print {{
  body {{ background: #fff; color: #000; }}
  body::before {{ display: none; }}
  .chat-fab, .chat-modal-overlay, .tab-bar {{ display: none !important; }}
  .tab-content {{ display: block !important; page-break-inside: avoid; }}
  .flashcard {{ break-inside: avoid; }}
}}
@media (max-width: 768px) {{
  .tab-btn {{ padding: 12px 16px; font-size: 0.65rem; }}
  .flashcard-grid {{ grid-template-columns: 1fr; }}
  .chat-fab {{ bottom: 20px; right: 20px; width: 48px; height: 48px; }}
  .nav-chapter-title {{ display: none; }}
}}
</style>
</head>
<body>

<!-- NAV -->
<nav class="top-nav">
  <div class="container">
    <div class="nav-left">
      <a href="dashboard.html" class="nav-back">← Dashboard</a>
      <div class="nav-divider"></div>
      <span class="nav-chapter-title">CH {ch_str} · {html_esc(title_en)}</span>
    </div>
    <div class="nav-right">
      <span class="nav-user" id="navUser"></span>
    </div>
  </div>
</nav>

<!-- CHAPTER HEADER -->
<section class="chapter-header">
  <div class="container">
    <div class="ch-number">Chapter {ch_str}</div>
    <h1 class="ch-title">{html_esc(title_en)}</h1>
    <p class="ch-subtitle">{html_esc(subtitle_zh)}</p>
  </div>
</section>

<!-- TABS -->
<div class="tab-bar">
  <button class="tab-btn active" data-tab="lecture">讲义正文</button>
  <button class="tab-btn" data-tab="flashcards">知识翻卡</button>
  <button class="tab-btn" data-tab="sop">SOP 工作单</button>
  <button class="tab-btn" data-tab="quiz">自测</button>
</div>

<!-- TAB: LECTURE -->
<div class="tab-content active" id="tab-lecture">
  <div class="container">
{lecture_html}
  </div>
</div>

<!-- TAB: FLASHCARDS -->
<div class="tab-content" id="tab-flashcards">
  <div class="container">
    <div class="flashcard-grid">
{flashcard_html}
    </div>
  </div>
</div>

<!-- TAB: SOP -->
<div class="tab-content" id="tab-sop">
  <div class="container">
    <div class="sop-placeholder">
{sop_html}
    </div>
  </div>
</div>

<!-- TAB: QUIZ -->
<div class="tab-content" id="tab-quiz">
  <div class="container">
{quiz_html}
  </div>
</div>

<!-- FOOTER -->
<footer class="site-footer">
  <div class="container">
    <p class="footer-text">© 2026 3HFIT × Arise — All Rights Reserved</p>
  </div>
</footer>

<!-- AI CHAT -->
<button class="chat-fab" onclick="openChat()">
  <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.2L4 17.2V4h16v12z"/></svg>
</button>
<div class="chat-modal-overlay" id="chatModal">
  <div class="chat-modal">
    <div class="chat-modal-icon">
      <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.2L4 17.2V4h16v12z"/></svg>
    </div>
    <h3>AI 助教</h3>
    <p>AI Teaching Assistant is coming soon. 循证 AI 助教即将上线。</p>
    <button class="chat-modal-close" onclick="closeChat()">Close</button>
  </div>
</div>

<script>
/* ========== AUTH ========== */
const student = JSON.parse(localStorage.getItem('sbst_student') || 'null');
if (!student) {{ window.location.href = 'index.html'; }}
else {{ document.getElementById('navUser').textContent = student.name; }}

/* ========== TABS ========== */
document.querySelectorAll('.tab-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  }});
}});

/* ========== QUIZ ========== */
function selectOpt(el) {{
  const siblings = el.parentElement.querySelectorAll('.quiz-opt');
  siblings.forEach(s => s.classList.remove('selected', 'correct', 'incorrect'));
  el.classList.add('selected');
}}

function checkQuiz(btn) {{
  const item = btn.closest('.quiz-item');
  const selected = item.querySelector('.quiz-opt.selected');
  if (!selected) return;
  
  const opts = item.querySelectorAll('.quiz-opt');
  const explanation = item.dataset.explanation;
  const feedback = item.querySelector('.quiz-feedback');
  
  opts.forEach(o => {{
    o.classList.remove('selected');
    if (o.dataset.correct === 'true') o.classList.add('correct');
    else if (o === selected) o.classList.add('incorrect');
  }});
  
  feedback.style.display = 'block';
  if (selected.dataset.correct === 'true') {{
    feedback.innerHTML = '✅ Correct! ' + explanation;
  }} else {{
    feedback.innerHTML = '❌ Incorrect. ' + explanation;
  }}
  
  btn.style.display = 'none';
  trackProgress('{ch_str}', 'quiz');
}}

/* ========== CHAT ========== */
function openChat() {{ document.getElementById('chatModal').classList.add('active'); }}
function closeChat() {{ document.getElementById('chatModal').classList.remove('active'); }}
document.getElementById('chatModal').addEventListener('click', e => {{
  if (e.target === e.currentTarget) closeChat();
}});

/* ========== PROGRESS TRACKING ========== */
function trackProgress(chapter, type) {{
  const progress = JSON.parse(localStorage.getItem('sbst_progress') || '{{}}');
  if (!progress[chapter]) progress[chapter] = {{}};
  progress[chapter][type] = true;
  progress[chapter].lastVisit = Date.now();
  localStorage.setItem('sbst_progress', JSON.stringify(progress));
}}

/* Mark visit on load */
(function() {{
  const progress = JSON.parse(localStorage.getItem('sbst_progress') || '{{}}');
  if (!progress['{ch_str}']) progress['{ch_str}'] = {{}};
  progress['{ch_str}'].lastVisit = Date.now();
  localStorage.setItem('sbst_progress', JSON.stringify(progress));
}})();
</script>
</body>
</html>'''


# ============================================================
# MAIN EXECUTION
# ============================================================
if __name__ == '__main__':
    print("Loading docx...")
    doc = Document(DOCX_PATH)
    
    for ch_num, sec_tag, title_en, subtitle_zh, p_start, p_end in CHAPTER_MAP:
        print(f"\nProcessing Chapter {ch_num}: {title_en} (paras {p_start}-{p_end})...")
        
        # Extract lecture content with tables
        lecture_html = extract_sections_with_tables(doc, p_start, p_end)
        
        # Generate SOP
        sop_html = generate_sop(ch_num, title_en, '')
        
        # Generate flashcards
        flashcard_html = generate_flashcards(ch_num)
        
        # Generate quiz
        quiz_html = generate_quiz(ch_num)
        
        # Build full HTML
        full_html = build_chapter_html(ch_num, title_en, subtitle_zh, lecture_html, sop_html, flashcard_html, quiz_html)
        
        # Write file
        filepath = os.path.join(SBST_DIR, f'ch{ch_num}.html')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_html)
        print(f"  Written: {filepath} ({len(full_html)} chars)")
    
    print("\n\nAll chapters processed!")
    print("Total chapters:", len(CHAPTER_MAP))
