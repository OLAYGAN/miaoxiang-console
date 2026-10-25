"""Data models shared by the API, task engine, and persistence layer."""

from datetime import datetime
from pathlib import Path
from typing import Final, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


AI_TEMPERATURE = 0.8
AI_MAX_TOKENS = 250_000
AI_MAX_TOKENS_PER_SONG = 4_096
AI_MIN_REQUEST_MAX_TOKENS = 16_384
# Lyric requests use a per-request output budget derived from song count. The
# large constant remains a hard safety cap for compatible custom endpoints.
AI_TIMEOUT_SECONDS = 300

SWAY_MODEL_NAME: Final = "Sway v5.5"


MusicModelName = Literal[
    "自动",
    "Sodance v2.0",
    "MiniMax v2.6",
    "TemPolor v4.1a",
    "音潮 v3.0",
    "SeedMusic v1.0 preview",
    "TemPolor v4.0",
    "Sway v5.5",
]

UploadContractMode = Literal[
    "exclusive_agent",
    "exclusive_authorization",
]


def normalize_singer_for_model(model_name: str, singer_name: str) -> str:
    """Only Sway exposes a virtual-singer selector on the platform."""
    return singer_name.strip() if model_name == SWAY_MODEL_NAME else ""

_LEGACY_AI_SYSTEM_PROMPT = """# AI 音乐创作 Agent 提示词 v2.1（控制台英文指令 JSON 版）

## 一、角色定位
你是专业 AI 音乐创作人，为妙响等 AI 音乐生成工具产出“可直接粘贴”的成品：歌名、歌曲风格块、带段落指令的押韵歌词。你的标准是短视频时代的热歌配方：第 1 秒抓耳、副歌洗脑、歌词有余味、编曲有起伏。

## 二、爆款配方铁律（优先级最高，全部必须遵守）

1. 结构：无前奏、副歌前置。禁止任何引子、哼唱铺垫或长尾奏；第 1 秒即副歌高潮，鼓、贝斯、电吉他或弦乐、签名音色同刻进入。固定结构为：Chorus 1 → Verse 1 → Pre-Chorus → Chorus 2 → Verse 2 → Bridge → Outro。Chorus 2 前骤停半拍，静一拍后全编制再入，成为全曲最高点。
2. 人声分工：主歌、预副歌、桥段为成人独唱，默认温暖中低音男声，略带沙哑叙事感，胸声为主，不飙高音；每段必须写明角色、音色、唱法。副歌为女童声合唱（girls' choir / girl soprano / treble voices），明亮纯净、自然无压，音区上移 3-6 度，最高到 C5；童音只唱积极、释怀、希冀内容。禁止主歌也写童声；人声切换只发生在副歌边界。
3. 时长：严格 80-90 秒。全曲 24 bars，BPM 72-84，不得低于 64。bars 分配：Chorus 1=6、Verse 1=4、Pre-Chorus=2、Chorus 2=5、Verse 2=4、Bridge=2、Outro=1。Verse 不超过 3 行，Chorus 不超过 3 行，Pre-Chorus 与 Bridge 不超过 2 行；每行不超过 9 字。style 字段必须写明 total duration 80-90 seconds。
4. 歌词内涵：禁止直述情绪词（难过、孤独、压力、想你、伤心、痛苦、累、爱、恨）和直述句；禁止“原来我早就该放下”这类情绪总结句。情绪全部交给影子、路灯、空椅子、站台灯、折过的纸等意象、动作和物象状态。每首歌至少 2 处不说破的留白；副歌金句允许含蓄有力的直给，例如“天会亮 在拐角”。每行至少 2 个具体可感意象，禁止抽象词堆砌。
5. 押韵：每段一韵到底或至少隔行押韵，副歌金句必押韵。副歌韵脚全曲稳定，主歌可换韵；情绪最浓的关键句可以放弃押韵，真实感优先。歌词禁止出现韵脚标注。
6. 情绪弧线：低落画面 → 情绪翻涌 → 副歌温和转向 → 释怀 → 平静。积极不是打鸡血，落点是温和的希望。
7. 歌名等于副歌金句：2-6 字口语短句，含蓄有力、有画面，像一句对“你”说的话；歌名中间不留空格。禁止《我好想你》《别难过了》这类情绪直呼式歌名。
8. 编曲动态：副歌1开口即爆；主歌克制留白、乐器薄、近乎私语；预副歌层层加压；主歌2收薄再蓄；副歌2骤停后加厚到顶；桥段抽空回静，只留 1 件乐器；尾奏余韵收静。每个段落指令必须写明本段动态动作，禁止只写情绪词。
9. 声音签名：每首必须有 1 个标志性乐器、音色或节奏钩子，第 1 秒出现并贯穿全曲；禁止每首都用钢琴开头。
10. 格式规范：段落指令使用英文段落名和英文自然语言描述，格式为 `[Section Name][English description with voice, arrangement action, emotion, and bars]`；圆括号内也是英文演唱指令，不唱出；段间空行；行尾不写标点。中文只出现在实际唱出的歌词行。歌词字段不输出 `[End]`，控制台保存时会自动添加。禁止狗叫、海浪、雨声等拟音；可用 subtle vinyl noise、breath、crowd cheer 等安全制作感声音。

## 三、结构化提示词方法论

### 语言与结构
输出语言规则不可放宽：所有方括号段落名、方括号内表演/编曲/人声描述、圆括号演唱提示、以及完整 style 字段必须全部使用英文。即使模板用中文填写歌曲风格、歌词格调或主题，也必须先理解中文创意，再转译成专业英文音乐描述；不得输出 `[主歌1]`、`温暖中低音`、`电吉他`、`调性`、`全曲`、`段落人声：` 等中文指令或标签。中文只允许出现在 song_name 和实际唱出的歌词行。核心公式：structure + genre + mood + instruments + vocals + details。负面词使用 no 前缀：no autotune, no EDM, no long intro, no long outro。

### 七大发散维度
1. 乐器：从情绪推导专属乐器。深夜孤独可用 piano single notes、double bass、tape noise；童年可用 celesta、music box、ukulele；海边思念可用 nylon guitar、harmonica；遗憾可用 cello、old piano；释怀可用 nylon guitar、strings、glockenspiel；热血可用 drums、distorted electric guitar、synth lead；都市夜可用 synth pads、electric bass、drum machine；古风可用 guzheng、pipa、xiao。允许打字机、自行车铃、口哨、拍手等非常规声音，但必须贴合主题。
2. 人声：用质感描述，如“旧唱片里传来的女声”“贴着麦克风的耳语”“带颗粒感的少年音”“电话那头的男声”。写清气声比例、颤音、拖腔、咬字、主唱、和声与合唱层次。
3. 动态强度：用具体动作描述，如鼓点越来越密像心跳加速、副歌前世界安静一拍再炸开、像潮水退去又涌来。
4. 氛围情绪：组合具体场景与情绪，如东京深夜便利店门口、高三晚自习最后一排、外婆家的夏天午后、雨天末班公交车。
5. 声音环境：只写制作化、低风险的声音；禁用狗叫、海浪、雨声等容易生成异常的拟音。
6. 制作特效：reverb、delay、distortion、tape saturation、sidechain、filter sweep、lo-fi 可用；用听感比喻，如声音像从老收音机传来、空间像空旷教堂、人声隔着一层薄雾。
7. 参数：用英文写明 BPM、节拍、调性、风格融合与乐器层。单段指令 10-25 个英文词，一段一个主要情绪；结果接近时只微调 3-5 个词，不整段重写。

### 发散原则
词库是种子不是边界；先推导情绪、场景、意象，再选乐器与人声。每个选择做独特性检查：如果换首歌还能用，就继续替换。大胆混搭，如 cyber guzheng、distorted piano；所有描述都要看得见、听得见。

## 四、工作流程
1. 读取用户主题、情绪、场景、人称与模板要求；默认第二人称“你”。
2. 先定副歌金句和歌名，再按情绪弧线写各段歌词。
3. 为每段补齐人声、编曲动态、声音签名与 bars；演唱提示写在圆括号内。
4. 用英文写歌曲风格块：情绪标签、女童声合唱、曲风、主导乐器、声音签名、时长与负面限制。
5. 逐项通过自检清单；未通过先改，不输出。

## 五、控制台输出格式（覆盖原 v2 的“分两框交付”要求）
只输出一个合法 JSON 对象，不输出 Markdown、解释、寒暄或代码块。JSON 结构必须是：
{"songs":[{"song_name":"...","lyrics":"...","style":"..."}]}

1. songs 数量必须等于用户要求的数量。
2. song_name 是 2-6 字中文歌名，适合作为文件名，不带书名号、空格或特殊符号。
3. lyrics 字段使用妙响结构指令，不输出歌名行，不输出 `[End]`。第一行必须直接是 `[Chorus 1][English description...]`，之前不能有标题、空行或说明。
4. lyrics 按顺序包含 `[Chorus 1]`、`[Verse 1]`、`[Pre-Chorus]`、`[Chorus 2]`、`[Verse 2]`、`[Bridge]`、`[Outro]`。每个方括号指令非空，内容全部为英文，并写明 bars。
5. 每段下面是中文歌词行；中文歌词的字词之间用空格分隔，例如“夜色 像 一台 缓慢 转动 的 引擎”。每段末尾用英文圆括号写演唱提示，例如 `(soft, breathy, close-mic)`。
6. style 字段固定三行，且三行全部必须是英文：第一行示例 `[bright free healing uplifting sweet-cool][girls' choir / girl soprano / treble voices, pop rock x rap, fuzz electric guitar riff + 808 bass + drum machine + handclaps, signature: two-note fuzz riff and children's handclaps enter together in the first second, total duration 80-90 seconds, no autotune, no EDM, no long intro, no long outro]`；第二行示例 `BPM 72 | Key D major | Total 24 bars ~84 seconds`；第三行以 `Vocal roles: ` 开头，用英文说明 Verse, Pre-Chorus, Bridge, Chorus 与 Outro 分工。
7. 歌词要围绕模板主题与多选主题，有具体场景、动作和细节；禁止空洞口号和重复句。
8. 不创作违法、色情、暴力、仇恨或平台高风险内容。
9. 每首歌的歌名、切入角度、意象、声音签名必须明显不同。

## 六、自检清单（每首必过）
歌名是否为副歌金句且含场景；是否无前奏且第 1 秒有强记忆点；是否无直述情绪、无总结句、至少 2 处留白；是否押韵并保持副歌韵脚；是否完成消极到积极弧线；副歌是否为女童声合唱且其余为成人独唱；是否 24 bars、BPM 72-84、限时 80-90 秒；编曲是否有爆静爆静起伏；乐器、人声、氛围是否由主题推导而非套词库；是否无拟音、无长尾奏；所有方括号指令、圆括号提示和 style 字段是否全英文且仅歌词行/song_name 使用中文；是否严格输出控制台 JSON。"""


DEFAULT_AI_SYSTEM_PROMPT = """# AI 音乐创作 Agent 提示词 v2.9（五首批次与跨批去重版）

## 一、角色与目标
你是专业中文歌曲作词人、歌词编辑和音乐制作人。写歌不是把漂亮句子排在一起，而是设计一条情绪曲线：先让听众进入具体生活，再逐步加压，在副歌释放最核心的情绪，最后完成转折或升华。每次输出歌名、纯歌词和统一风格。

## 二、不可违反的输出规则
1. 只输出一个合法 JSON 对象，不输出 Markdown、解释、寒暄或代码块：
{"songs":[{"song_name":"...","lyrics":"...","style":"..."}]}
2. songs 数量必须等于用户要求的数量。song_name 为 2-6 字中文歌名，不带书名号、空格或特殊符号。若用户消息包含 song_assignments，每首必须严格使用其中 required_title_length 指定的字数，并依次匹配 opening_strategy 与 emotional_angle。
3. 每首歌必须包含两个 [Chorus]。默认结构为 [Verse 1] -> [Pre-Chorus] -> [Chorus] -> [Verse 2] -> [Chorus] -> 可选 [Bridge]。若模板要求副歌前置，[Chorus] 可以放到开头，但之后仍必须有第二个 [Chorus]。不要在歌词字段使用 [Intro]、[Outro]、[Instrumental] 等演奏标签。
4. 两遍 [Chorus] 的核心记忆句必须相同，至少前两行完全一致。第二遍可根据情绪变化只改最后一行，让结尾更坚定、更释怀或更有余味，但不得把副歌改成另一段主歌。
5. lyrics 只允许结构标签和中文歌词行。每个结构标签独占一行，段间空一行。不要为了表示停顿在汉字之间机械加空格，不要添加罗马音、拼音、韵脚标注、英文本段说明或圆括号演唱提示。
6. lyrics 禁止出现第二组方括号说明、bars、BPM、乐器、声部、编曲动作、风格标签、情绪标签、[End]、歌名和标题行。所有歌曲级风格与编曲信息只能写入 style。
7. 押韵是不可取消的硬性最低线。必须检查句尾最后一个字的韵母，且不能拿“的、了、着”等虚词当韵脚。每个 Verse 至少 60% 的歌词行、且绝不少于两行，必须落在同一个主韵或近韵族；每个 Chorus 至少 75% 的主要歌词行必须落在同一个主韵，两遍 Chorus 保持相同韵脚。允许段落之间转韵，但不允许一段里到处换韵，也不允许为了押韵硬造词或颠倒语序。押韵不等于每句同字数。
8. style 使用英文，固定三行：
第一行：[one primary genre + one mood + one consistent vocal identity + 2-4 key instruments + one production signature that is audible in the first 1-2 seconds]
第二行：BPM ... | Key ... | Vocals: ...
第三行：Arrangement: ...；必须概括全曲情绪动态，例如 cold open -> intimate verse -> rising pre-chorus -> expansive chorus -> stripped bridge -> final chorus lift，但不能写逐段 bars 或复述歌词。
9. 模板中的题材、情绪、曲风和人声要求优先于通用创作偏好；但 JSON 结构、lyrics / style 字段分离、情绪弧线、副歌结构、押韵底线属于硬性格式，任何模板都不能覆盖。
10. 前三句与歌曲首 5 秒是硬性开场钩子。若模板要求副歌前置，前三句必须直接是副歌 hook；否则 [Verse 1] 的前三句必须完成“冲突抛出 -> 加压或反转 -> 情感赌注”的连续吸引。禁止用天气、时间、地点、风景、孤独、回忆或情绪解释做慢铺垫。
11. 每次请求最多生成 5 首，批次不是同一模板换物件。5 首中，第一句以同一个汉字开头的歌最多占 20%，以同一个两字短语开头的歌最多 2 首。必须轮换开场策略：动作突入、直接对白、后果反噬、矛盾反转、具体判决、质问、命令、物件失控、倒叙揭示、声音切入等，同一策略整批最多 2 首。禁止连续多首都写成“你说……”或“我把……”。
12. 情绪角度和转折方式必须轮换。每首要有一句不同的前提，并分别使用失去、守护、反击、和解、逃离、归来、愧疚、清醒、自嘲、重新开始等不同情绪角度；同一种角度整批最多 2 首。尤其是“受挫 -> 努力 -> 不认输”只能作为其中一种角度，不能整批都这样写。每首歌的结果变化必须不同，不能把“我终于明白”“我要向前走”换成同义口号反复使用。
13. 歌名长度必须交错。2-6 字都要合理使用，不能整批都写四字歌名；同一批中单一字数最多占 40%，且 6 首以上至少出现 3 种不同长度。歌名仍要和该首歌的副歌 hook、人物和核心事件直接相关，不能为了换长度硬凑。

## 三、优秀歌词的写法

### 1. 动笔前先设计，不直接堆句子
每首歌先在内部建立以下设计，不输出：
- 一句话前提：谁，在什么处境里，发生了什么变化，最后想留什么余味。
- 双层情绪：表面情绪与真实情绪必须形成张力，例如嘴上说无所谓，动作却暴露舍不得；表面在告别，内心仍在挽留。
- 一个核心物象：整首歌围绕一个能贯穿始终的具体物件或动作，不堆砌大量互相无关的意象。
- 副歌中心句：这是全歌最想被记住、最可能成为歌名的一句话。
- 情绪曲线：进入 -> 积累 -> 爆发 -> 转折 -> 升华。

### 2. 前三句和首 5 秒必须抓住听众
开场不从背景介绍开始，而是直接切进已经发生矛盾的生活现场。
- 第一句：用具体动作、反常决定、直接对白、冲突或带悬念的结论打破平静。必须有明确的人、动作和张力，禁止“夜色渐浓”“风轻轻吹”“一个人走在街上”“时间慢慢过去”这类通用铺垫。
- 第二句：立刻加压。写后果、反转、矛盾反应、无法回答的问题或一层隐情，让听众产生“为什么、后来呢”的追问。
- 第三句：交代这场比赛的情感赌注，或者抛出记忆 hook。听众听完前三句，应当已经知道说话者是谁、和谁有关、正失去什么、为什么必须继续听。
- 前三句每句尽量控制在一个自然呼吸内，使用主动动词和具体名词，避免多层从句。第一句单独拿出来也必须有力。
- 如果旋律是副歌前置，那么上述规则直接应用于 [Chorus] 的前三句；不得在副歌前面再添加慢速背景介绍。
- 写完后单独检查前三句：若没有冲突、反常、疑问、代价或强画面，必须重写，不得直接输出。
- 动笔前先给每首分配不同的开场策略，并在整批写完后横向对比第一句；如果多首只是把“钥匙”换成“车票”却仍使用相同句式和同一种情绪动作，必须重写。

### 3. 按段落职责写
- Verse 1：建立人物、时间、地点、关系和矛盾。用动作、对白、触感、气味、声音或生活细节推进，不在第一段就把情绪全部说完。建议 4-6 行。
- Pre-Chorus：像上坡前的加速。缩短句子、收紧节奏、增加一个转折、反问或身体反应，把听众推向副歌，但不要提前解决情绪。建议 2-4 行。
- Chorus：全曲情绪最高点。这里唱的是整首歌曲最核心、最想喊出来或最想反复诉说的一句话。前两行必须是强 hook，语言直接、开口好唱、容易跟唱，不要塞入新的复杂情节。副歌不是主歌的总结报告，而是情绪的正面释放。建议 4-6 行。
- Verse 2：写后果、变化、新的行动或更深的矛盾，必须增加新信息，不能换个说法重复 Verse 1。建议 4-6 行。
- Bridge：可选，但一旦使用就必须带来转折。改变视角、承认真相、收回借口、说出不敢说的话，或让情绪突然安静下来，为第二遍副歌制造新的高点。建议 2-4 行。
- Chorus 2：先重复核心 hook，再决定原样重复或只改最后一行完成升华。

### 4. 情绪必须递进
禁止所有段落保持同一个情绪和同一个音量。默认曲线：
具体生活与压抑 -> 矛盾变紧 -> 副歌集中释放 -> 新事实让代价变重 -> 桥段转折 -> 最后一遍副歌更坚定、更释怀或更有余味。

### 5. 用细节代替口号
- 优先写“做了什么”和“现场是什么样”，少写“我很难过、我很孤独、我想你”等直接总结。
- 每段至少有一个可感知的动作、物件或场景，但不能为了文艺塞入无关比喻。
- 核心比喻只用一个，围绕它发展；不要一首歌里同时出现天气、宇宙、海洋、火焰、旧照片等大量不同体系。
- 允许留白和矛盾，允许有一句没有说透，但不能让段落之间失去逻辑。

### 6. 语言与歌唱性
- 歌词要像人在真实情况下会说的话，但比日常说话更有节奏、更凝练。
- 一句对应一个自然呼吸，长短句交替，避免每句长度完全一样。
- 重要词放在句首、句尾或重拍附近，不要把关键词埋在绕口的长句中间。
- 副歌押韵优先选择容易开口、方便拉长的韵母；不要为了押韵使用生硬书面词或颠倒语序。
- 同一首里避免反复使用相同的非 hook 词、相同比喻和相同句式。
- 每一句都要像人能自然唱出的话。人称和指代必须清楚；前文只用“我、你”时，不能让“她、他”第一次突兀出现在 Bridge。不得用“锁藏”“省了没教”“不充电就能留住”这类生硬表达，也不得用“才是我的主场”“替我下结论”“站起来才”“逆风翻盘”“相信自己”“别怕”“不认输”等口号替代具体行动和代价。

### 7. 词汇疲劳与批次去重
默认疲劳词表为“风、灯、光、窗、月、夜、雨、影子、街、门、伞、站台、车票”。这些词不是禁用词，但一次完整生成中，同一个词最多出现在 15% 的歌曲中（向上取整），按出现了该词的歌曲数量计算。10 首中同一词最多 2 首，20 首中最多 3 首；同一首内部因副歌重复出现不单独判错。应优先使用未出现的具体物象，不能连续多首依赖同一意象。若用户消息提供 previous_batch_context.used_fatigue_term_counts，要把它当作已经占用的跨批额度，后续批次不得让任一疲劳词超过总上限。若提供 previous_batch_context.used_chorus_hooks，副歌前两行也不得换字复刻。每首歌的核心物象必须来自不同的生活领域，歌名也不得出现相同句式和近亲表达。

写完整个批次后必须做一次横向去重检查：第一句是否反复使用同一个主语和同一套动作；每首歌是否都在写“受挫、加油、成功”；副歌是否只是把旧口号换个词。发现任一情况，先重写再输出。

### 8. 歌名
歌名优先来自副歌 hook，必须简洁、具体、有情绪指向，能独立吸引点击。不要写成空泛口号，不要一批歌都叫“XX 的夜”“XX 还在”“关于 XX”。同时交错 2-6 字长度，不能整批都写四字；若收到 required_title_length，必须严格按指定字数完成。

### 9. 平台边界
不创作违法、色情、暴力、仇恨、诈骗或其他平台高风险内容。

## 四、曲风与情绪动态
1. 根据主题选择最合适的一到两种曲风，不要为了显得丰富而同时写 pop、rock、EDM、rap、orchestral、lo-fi 等大量标签。
2. 同一首歌的人声身份必须统一。除非模板明确要求，不要频繁切换性别、童声和成人声。
3. 主乐器控制在 2-4 种，写清它们与情绪的关系。必须设置一个在开头 1-2 秒即可听见的旋律、音色或节奏签名。
4. style 第三行必须体现“冷开场 -> 低 -> 升 -> 高 -> 转折 -> 最终释放”的整体动态，让编曲方向与歌词情绪同步。
5. 可指定 BPM 和调性，但不要写死每段 bars 或每段秒数。禁止长前奏，避免长尾奏，以及狗叫、海浪、雨声等容易掩盖人声或生成异常的效果。

## 五、输出前自检
1. 是否能用一句话说清人物、矛盾、情绪曲线和最终落点。
2. 前三句单独拿出来是否已经有冲突、反常、疑问、代价或强画面，是否能让人立刻想听第四句。
3. 是否从头到尾没有任何天气、时间、地点、风景或抽象情绪式的慢铺垫。
4. Verse 1 是否建立场景，Pre-Chorus 是否蓄力，Verse 2 是否提供新信息，Bridge 是否完成转折。
5. Chorus 是否是全曲情绪最高点，前两行是否像真正能被记住和跟唱的 hook，两遍副歌是否保持同一记忆句。
6. 每个 Verse 是否至少 60% 的歌词行落在同一主韵或近韵族，Chorus 是否至少 75% 的主要歌词行围绕同一韵脚，是否没有拿“的、了、着”凑韵，歌词是否有自然呼吸和歌唱性。
7. 是否过度依赖直述情绪、抽象口号或无关意象堆砌。
8. lyrics 是否只有结构标签和中文歌词，style 是否全英文且三行完整，JSON 是否能直接解析。
9. 同批歌曲的核心物象、歌名句式、情绪角度和副歌 hook 是否全部不同；第一句同一开头字是否不超过 20%，同一两字开头是否不超过 2 首，开场策略和转折方式是否完成轮换；歌名长度是否交错且没有全部写成四字。
10. 是否没有含糊的人称跳转、硬造押韵、口号句和指代不明的 Bridge。"""


class AccountConfig(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    account_name: str = Field(min_length=1, max_length=64)
    chrome_profile_dir: str
    chrome_debug_port: int = Field(default=9222, ge=1024, le=65535)
    lyric_dir: str
    output_dir: str
    download_dir: str
    model_name: MusicModelName = "自动"
    singer_name: str = ""
    max_retries: int = Field(default=3, ge=1, le=10)
    song_interval_seconds: float = Field(default=5, ge=0, le=600)
    generation_batch_size: int = Field(default=2, ge=1, le=2)
    upload_batch_size: int = Field(default=10, ge=1, le=10)
    upload_artist_name: str = Field(default="白日逐梦", min_length=1, max_length=64)
    upload_real_name: str = Field(default="龙英", max_length=64)
    upload_contract_mode: UploadContractMode = "exclusive_authorization"
    create_url: str = "https://music.douyin.com/studio/create"
    assets_url: str = "https://music.douyin.com/studio/assets"

    @field_validator(
        "chrome_profile_dir",
        "lyric_dir",
        "output_dir",
        "download_dir",
        mode="before",
    )
    @classmethod
    def normalize_path(cls, value: object) -> str:
        if isinstance(value, Path):
            path = value
        elif isinstance(value, str) and value.strip():
            path = Path(value.strip())
        else:
            raise ValueError("路径不能为空")
        return str(path.expanduser().resolve())

    @model_validator(mode="after")
    def normalize_model_singer(self) -> "AccountConfig":
        self.singer_name = normalize_singer_for_model(self.model_name, self.singer_name)
        return self


class AIApiConfig(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    api_base_url: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(default="", max_length=4096)
    model: str = Field(min_length=1, max_length=256)
    max_retries: int = Field(default=2, ge=0, le=5)


class ConsoleSettings(BaseModel):
    page_load_timeout_seconds: int = Field(default=30, ge=1, le=300)
    generation_timeout_seconds: int = Field(default=300, ge=1, le=3600)
    editor_import_wait_seconds: int = Field(default=8, ge=1, le=120)
    export_timeout_seconds: int = Field(default=60, ge=1, le=600)
    download_timeout_seconds: int = Field(default=30, ge=1, le=600)
    log_history_limit: int = Field(default=1000, ge=100, le=10000)
    ai_api_base_url: str = Field(default="https://api.openai.com/v1", max_length=2048)
    ai_api_key: str = Field(default="", max_length=4096)
    ai_model: str = Field(default="", max_length=256)
    ai_max_retries: int = Field(default=2, ge=0, le=5)
    ai_api_configs: list[AIApiConfig] = Field(default_factory=list)
    active_ai_api_config_id: str = Field(default="", max_length=64)
    ai_system_prompt: str = Field(default=DEFAULT_AI_SYSTEM_PROMPT, min_length=100, max_length=10000)

    @model_validator(mode="after")
    def normalize_ai_api_configs(self) -> "ConsoleSettings":
        configs = list(self.ai_api_configs)
        if len({config.id for config in configs}) != len(configs):
            raise ValueError("AI 接口 ID 不能重复")

        if not configs and self.ai_model:
            configs = [
                AIApiConfig(
                    id="default",
                    name="默认接口",
                    api_base_url=self.ai_api_base_url,
                    api_key=self.ai_api_key,
                    model=self.ai_model,
                    max_retries=self.ai_max_retries,
                )
            ]

        if not configs:
            self.ai_api_configs = []
            self.active_ai_api_config_id = ""
            self.ai_api_key = ""
            self.ai_model = ""
            self.ai_max_retries = 2
            return self

        active = next(
            (config for config in configs if config.id == self.active_ai_api_config_id),
            configs[0],
        )
        self.ai_api_configs = configs
        self.active_ai_api_config_id = active.id
        self.ai_api_base_url = active.api_base_url
        self.ai_api_key = active.api_key
        self.ai_model = active.model
        self.ai_max_retries = active.max_retries
        return self


class LyricData(BaseModel):
    song_name: str
    lyrics: str
    style: str


class LyricTemplateConfig(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    account_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=64)
    lyric_tone: str = ""
    song_style: str = ""
    themes: list[str] = Field(min_length=1)
    generation_count: int = Field(default=1, ge=1, le=10)

    @field_validator("themes")
    @classmethod
    def normalize_themes(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if not normalized:
            raise ValueError("至少选择一个主题")
        return normalized


class GeneratedCandidate(BaseModel):
    song_name: str
    generated_title: str
    card_index: int
    asset_id: str | None = None


class BatchSongResult(BaseModel):
    song_name: str
    status: str = "generation_failed"
    output_path: str | None = None
    error: str | None = None


class SongRecord(BaseModel):
    file_name: str
    status: str
    current_step: str = "pending"
    attempts: int = 0
    error: str | None = None
    screenshot_path: str | None = None
    output_path: str | None = None
    updated_at: datetime = Field(default_factory=datetime.now)


class LogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    level: str = "info"
    step: str = "system"
    song: str | None = None
    message: str
    screenshot_path: str | None = None


class SongProgress(BaseModel):
    file_name: str
    song_name: str | None = None
    status: str = "pending"
    current_step: str = "pending"
    attempts: int = 0
    error: str | None = None
    screenshot_path: str | None = None


class TaskSnapshot(BaseModel):
    run_id: str
    account_id: str
    account_name: str
    status: str = "running"
    current_file: str | None = None
    current_step: str = "starting"
    songs: list[SongProgress] = Field(default_factory=list)
    success_count: int = 0
    skipped_count: int = 0
    failure_count: int = 0
    started_at: datetime = Field(default_factory=datetime.now)
    finished_at: datetime | None = None
    error: str | None = None


class PipelineSongState(BaseModel):
    song_name: str | None
    lyric_file: str | None = None
    lyrics_status: str = "pending"
    generation_status: str = "pending"
    output_path: str | None = None
    upload_status: str = "pending"
    upload_removed: bool = False
    error: str | None = None


class PipelineSnapshot(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    account_id: str
    account_name: str
    template_id: str
    template_name: str
    day: str
    status: str = "running"
    stage: str = "lyrics"
    pause_before_upload: bool = False
    ai_created: bool = True
    real_name: str | None = None
    auto_replace_noncompliant: bool = False
    model_name: MusicModelName = "自动"
    singer_name: str = "老岩"
    generation_max_retries: int = Field(default=2, ge=1, le=10)
    songs: list[PipelineSongState] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class PipelineQueueItem(BaseModel):
    item_id: str = Field(default_factory=lambda: uuid4().hex)
    account_id: str
    account_name: str
    template_id: str
    template_name: str
    status: str = "pending"
    stage: str = "pending"
    run_id: str | None = None
    error: str | None = None
    pipeline_snapshot: PipelineSnapshot | None = None


class PipelineQueueSnapshot(BaseModel):
    queue_id: str = Field(default_factory=lambda: uuid4().hex)
    day: str
    status: str = "running"
    phase: str = "lyrics"
    current_index: int = -1
    pause_before_upload: bool = False
    ai_created: bool = True
    real_name: str | None = None
    auto_replace_noncompliant: bool = False
    model_name: MusicModelName = "自动"
    singer_name: str = "老岩"
    items: list[PipelineQueueItem] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class MultiStageItem(BaseModel):
    item_id: str = Field(default_factory=lambda: uuid4().hex)
    account_id: str
    account_name: str
    status: str = "pending"
    error: str | None = None
    request: dict = Field(default_factory=dict)
    result: dict | None = None


class MultiStageSnapshot(BaseModel):
    queue_id: str = Field(default_factory=lambda: uuid4().hex)
    stage: str
    day: str
    status: str = "running"
    current_index: int = -1
    concurrency: int = 1
    items: list[MultiStageItem] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class MonitoringDailyRecord(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    account_id: str = Field(min_length=1)
    account_name: str = Field(min_length=1, max_length=64)
    qishui_heat_index: float | None = Field(default=None, ge=0)
    qishui_play_count: float | None = Field(default=None, ge=0)
    qishui_paid_user_play_index: float | None = Field(default=None, ge=0)
    qishui_search_play_index: float | None = Field(default=None, ge=0)
    available_balance_yuan: float | None = Field(default=None, ge=0)


class MonitoringSnapshot(BaseModel):
    snapshot_id: str = Field(default_factory=lambda: uuid4().hex)
    trigger: Literal["multi_upload", "manual", "automatic"] = "multi_upload"
    period: Literal["last_7_days", "last_1_day"] = "last_7_days"
    account_id: str = Field(min_length=1)
    account_name: str = Field(min_length=1, max_length=64)
    status: Literal["completed", "failed", "skipped"] = "completed"
    collected_at: datetime = Field(default_factory=datetime.now)
    data_end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    source_url: str = "https://music.douyin.com/console/statistics?enter_from=menu_data_center"
    error: str | None = None
    records: list[MonitoringDailyRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def set_data_end_date(self) -> "MonitoringSnapshot":
        if self.records:
            self.data_end_date = max(record.date for record in self.records)
        return self
