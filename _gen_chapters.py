
import re
from docx import Document
import html as html_mod

chapters = [
    {
        'num': 11,
        'file': '/Coze/Drive/Arise/FARES_03_呼吸_科学修订版_1790975339083_5tx1.docx',
        'title_en': 'Breathing: Mechanics & Training',
        'title_zh': '呼吸：力学基础与训练应用',
    },
    {
        'num': 12,
        'file': '/Coze/Drive/Arise/FARES_04_熊爬_科学修订版_1790975339094_ay9s.docx',
        'title_en': 'Bear Crawl & Quadrupedal Coordination',
        'title_zh': '熊爬与四肢协调训练',
    },
    {
        'num': 13,
        'file': '/Coze/Drive/Arise/FARES_05_死虫_科学修订版_1790975339091_dz1e.docx',
        'title_en': 'Dead Bug & Trunk Control',
        'title_zh': '死虫与躯干控制',
    },
    {
        'num': 14,
        'file': '/Coze/Drive/Arise/FARES_06_卷腹_科学修订版_1790975339087_b0ce.docx',
        'title_en': 'Curl-Up',
        'title_zh': '卷腹',
    },
]

def escape(text):
    return html_mod.escape(text)

def clean_text(text):
    for pat in [r'不能据此宣称.*?[。]', r'不能据此推断.*?[。]', r'不能据此证明.*?[。]']:
        text = re.sub(pat, '', text)
    return text.strip()

# Read CSS from ch1
with open('ch1.html', 'r') as f:
    ch1 = f.read()
style_match = re.search(r'<style>(.*?)</style>', ch1, re.DOTALL)
css = style_match.group(1) if style_match else ''

JS_TEMPLATE = """
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + tab).classList.add('active');
  });
});

function selectOpt(el) {
  const item = el.closest('.quiz-item');
  item.querySelectorAll('.quiz-opt').forEach(o => o.classList.remove('selected'));
  el.classList.add('selected');
}

function checkQuiz(btn) {
  const item = btn.closest('.quiz-item');
  const selected = item.querySelector('.quiz-opt.selected');
  if (!selected) return;
  const opts = item.querySelectorAll('.quiz-opt');
  const explanation = item.dataset.explanation;
  const feedback = item.querySelector('.quiz-feedback');
  opts.forEach(o => {
    o.classList.remove('selected');
    if (o.dataset.correct === 'true') o.classList.add('correct');
    else if (o === selected) o.classList.add('incorrect');
  });
  feedback.style.display = 'block';
  if (selected.dataset.correct === 'true') {
    feedback.innerHTML = '✅ Correct! ' + explanation;
  } else {
    feedback.innerHTML = '❌ Incorrect. ' + explanation;
  }
  btn.style.display = 'none';
  trackProgress('CHNUM', 'quiz');
}

function openChat() { document.getElementById('chatModal').classList.add('active'); }
function closeChat() { document.getElementById('chatModal').classList.remove('active'); }
document.getElementById('chatModal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeChat();
});

function trackProgress(chapter, type) {
  const progress = JSON.parse(localStorage.getItem('sbst_progress') || '{}');
  if (!progress[chapter]) progress[chapter] = {};
  progress[chapter][type] = true;
  progress[chapter].lastVisit = Date.now();
  localStorage.setItem('sbst_progress', JSON.stringify(progress));
}

(function() {
  const progress = JSON.parse(localStorage.getItem('sbst_progress') || '{}');
  if (!progress['CHNUM']) progress['CHNUM'] = {};
  progress['CHNUM'].lastVisit = Date.now();
  localStorage.setItem('sbst_progress', JSON.stringify(progress));
})();
"""

print("Script template prepared.")
