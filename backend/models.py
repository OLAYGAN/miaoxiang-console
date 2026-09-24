"""Data models shared by the API, task engine, and persistence layer."""

from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


AI_TEMPERATURE = 0.8
AI_MAX_TOKENS = 250_000
# One generous fixed limit for all request sizes; generation normally finishes
# well before this, while a dead connection still cannot hang the console forever.
AI_TIMEOUT_SECONDS = 300

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

DEFAULT_AI_SYSTEM_PROMPT = """# AI 音乐创作 Agent 提示词 v2.1（控制台英文指令 JSON 版）

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


class AccountConfig(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    account_name: str = Field(min_length=1, max_length=64)
    chrome_profile_dir: str
    chrome_debug_port: int = Field(default=9222, ge=1024, le=65535)
    lyric_dir: str
    output_dir: str
    download_dir: str
    model_name: MusicModelName = "自动"
    singer_name: str = "老岩"
    max_retries: int = Field(default=3, ge=1, le=10)
    song_interval_seconds: float = Field(default=5, ge=0, le=600)
    generation_batch_size: int = Field(default=2, ge=1, le=2)
    upload_batch_size: int = Field(default=10, ge=1, le=10)
    upload_artist_name: str = Field(default="白日逐梦", min_length=1, max_length=64)
    upload_real_name: str = Field(default="龙英", max_length=64)
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
    ai_system_prompt: str = Field(default=DEFAULT_AI_SYSTEM_PROMPT, min_length=100, max_length=10000)


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
    current_index: int = -1
    pause_before_upload: bool = False
    ai_created: bool = True
    real_name: str | None = None
    auto_replace_noncompliant: bool = False
    items: list[PipelineQueueItem] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
