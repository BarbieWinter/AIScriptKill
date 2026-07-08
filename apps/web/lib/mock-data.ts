/**
 * Mock 数据系统
 * 当无后端时，提供完整的模拟数据和行为
 *
 * 数据完全遵循 API_REFERENCE.md 中定义的结构
 */

// ─── 剧本包 ───

export const mockPackages = [
  {
    id: "snow-village",
    title: "雪乡连环杀人事件",
    description:
      "雪乡，一个被大雪覆盖的东北村庄。新年将至，村子里却接连发生命案……除夕夜，村口饭店老板王大达热情地招待着客人们，但一桩离奇的命案打破了这份宁静。玩家将扮演六名游客之一，通过调查、对话、推理，揭开雪乡隐藏多年的秘密。",
    poster_url: "",
    difficulty: 3,
    duration_minutes: 120,
    genre: ["悬疑", "推理", "惊悚"],
    status: "published" as const,
    player_count: 1,
    rating: 4.5,
    rating_count: 128,
  },
];

// ─── 角色定义 ───

export const mockCharacters = [
  {
    id: "zhuosiyuan",
    name: "卓司元",
    portrait_url: "",
    playable: true,
    is_dm_alter_ego: false,
    personality: "细心、谨慎，观察力敏锐",
    tagline: "我是个普通的游客……只是碰巧注意到了一些细节。",
    background: "来自城市的保险调查员，因年假来到雪乡度假。职业习惯让他对周围的一切都保持警惕。",
    knows: ["基本的侦查技巧", "逻辑推理"],
    doesnt_know: ["雪乡的往事", "本地人际关系"],
  },
  {
    id: "cuikaiqiang",
    name: "崔铠强",
    portrait_url: "",
    playable: true,
    is_dm_alter_ego: false,
    personality: "冲动、直率，行动派",
    tagline: "这村子有问题，我敢肯定。",
    background: "退伍军人，性格暴躁但正义感强。曾来过雪乡一次，对这里有些模糊的记忆。",
    knows: ["野外生存", "格斗技巧", "雪乡地形"],
    doesnt_know: ["自己的过去"],
  },
  {
    id: "likaixin",
    name: "李开心",
    portrait_url: "",
    playable: true,
    is_dm_alter_ego: false,
    personality: "温暖、善良，共情力强",
    tagline: "大家冷静一下！一定能找到真相的。",
    background: "小学教师，天性乐观善良。来雪乡是为了拍摄雪景照片。",
    knows: ["心理学常识", "本地民俗"],
    doesnt_know: ["人性的黑暗面"],
  },
  {
    id: "wangqi",
    name: "王琪",
    portrait_url: "",
    playable: true,
    is_dm_alter_ego: false,
    personality: "胆小、敏感，直觉敏锐",
    tagline: "我……我昨晚好像看到了什么……",
    background: "自由撰稿人，来雪乡寻找创作灵感。性格软弱但第六感极强。",
    knows: ["小道消息", "八卦信息"],
    doesnt_know: ["面对危险的勇气"],
  },
  {
    id: "xiaomeng",
    name: "萧萌",
    portrait_url: "",
    playable: true,
    is_dm_alter_ego: false,
    personality: "天真、活泼，好奇心强",
    tagline: "哇！这里好像侦探小说里的场景！",
    background: "大学生，寒假和朋友一起来雪乡玩。喜欢看推理小说，没想到自己会身临其境。",
    knows: ["推理小说知识", "网络信息"],
    doesnt_know: ["现实中的危险"],
  },
  {
    id: "chenji",
    name: "陈吉",
    portrait_url: "",
    playable: true,
    is_dm_alter_ego: false,
    personality: "冷静、理性，高深莫测",
    tagline: "呵呵，越来越有意思了。",
    background: "神秘商人，没人知道他的真实身份。总是面带微笑，但眼神中藏着什么。",
    knows: ["各种知识", "人脉关系"],
    doesnt_know: ["自己的真实目的"],
  },
  {
    id: "wangdada",
    name: "王大达",
    portrait_url: "",
    playable: false,
    personality: "热情但心虚，表面豪爽实则紧张",
    tagline: "你们可算来了！我都等半天了！",
    background: "雪乡村口饭店的老板，在雪乡生活了二十年。热情好客，但这些天有些心神不宁。",
    knows: ["雪乡所有人", "村里的秘密"],
    doesnt_know: ["凶手的真实身份"],
  },
  {
    id: "chengjun",
    name: "程俊",
    portrait_url: "",
    playable: false,
    personality: "沉默寡言，眼神躲闪",
    tagline: "（沉默不语）",
    background: "雪乡的猎户，独来独往。没有人了解他的过去。",
    knows: ["深山密道", "多年前的真相"],
    doesnt_know: ["如何面对过去"],
  },
  {
    id: "dm",
    name: "DM",
    portrait_url: "",
    playable: false,
    is_dm_alter_ego: true,
    personality: "全知全能的叙事者",
    tagline: "故事，开始了。",
    background: "超越故事本身的存在，引导玩家经历一切。",
    knows: ["一切"],
    doesnt_know: [],
  },
];

// ─── 场景定义 ───

export const mockScenes = [
  {
    id: "village_entrance",
    name: "雪乡村口",
    description: "大雪纷飞的村口，远处能看到零星的灯光。村口的招牌被雪覆盖了一半。",
    bg_color: "from-[#1a1a2e] to-[#0a0a0b]",
    hotspots: [
      { id: "signboard", label: "🔍 村口招牌", x: 30, y: 25, width: 15, height: 20 },
      { id: "snow_tracks", label: "🔍 雪地脚印", x: 60, y: 70, width: 20, height: 15 },
      { id: "restaurant_door", label: "🚪 饭店大门", x: 75, y: 30, width: 18, height: 25 },
    ],
  },
  {
    id: "restaurant_hall",
    name: "饭店大厅",
    description: "温暖的饭店大厅，炉火烧得正旺。墙上挂着老照片和年画。",
    bg_color: "from-[#2a1f1a] to-[#1a1410]",
    hotspots: [
      { id: "kitchen_door", label: "🚪 厨房门", x: 10, y: 20, width: 12, height: 20 },
      { id: "photo_wall", label: "🔍 照片墙", x: 40, y: 15, width: 20, height: 25 },
      { id: "back_door", label: "🚪 后门", x: 80, y: 30, width: 15, height: 22 },
      { id: "bar_counter", label: "🔍 吧台", x: 50, y: 55, width: 25, height: 20 },
    ],
  },
  {
    id: "back_alley",
    name: "后门小巷",
    description: "饭店后门的狭窄小巷，积雪堆在墙角。黑暗中似乎有什么在闪着光。",
    bg_color: "from-[#0f0f1a] to-[#05050a]",
    hotspots: [
      { id: "broken_glass_spot", label: "🔍 碎玻璃", x: 30, y: 60, width: 15, height: 12 },
      { id: "blood_stain", label: "🔍 暗色污渍", x: 55, y: 50, width: 12, height: 10 },
      { id: "footprints", label: "🔍 脚印", x: 40, y: 75, width: 20, height: 15 },
    ],
  },
  {
    id: "crime_scene",
    name: "雪地现场",
    description: "警戒线围起来的案发现场。雪地上的轮廓格外刺眼。",
    bg_color: "from-[#1a1a2e] to-[#0a0505]",
    hotspots: [
      { id: "body_outline", label: "🔍 尸体轮廓", x: 45, y: 55, width: 15, height: 18 },
      { id: "bloody_knife_spot", label: "🔍 可疑刀具", x: 65, y: 70, width: 10, height: 8 },
      { id: "torn_cloth", label: "🔍 碎布条", x: 30, y: 60, width: 8, height: 6 },
      { id: "footprint_trail", label: "🔍 脚印踪迹", x: 50, y: 80, width: 30, height: 12 },
    ],
  },
];

// ─── 线索定义 ───

export const mockClues = [
  {
    id: "broken_glass",
    name: "碎玻璃碴",
    image_url: "",
    description: "饭店后门的地上有一些破碎的玻璃杯碎片，边缘沾有少量暗红色物质。",
    is_key: false,
    importance: 2,
    status: "locked" as const,
    stage: "act1_investigation",
    scene_id: "back_alley",
    hotspot_id: "broken_glass_spot",
  },
  {
    id: "bloody_footprint",
    name: "带血脚印",
    image_url: "",
    description: "雪地上有一串带血的脚印，从后门方向延伸到小巷深处。脚印尺码约42码。",
    is_key: true,
    importance: 4,
    status: "locked" as const,
    stage: "act1_investigation",
    scene_id: "back_alley",
    hotspot_id: "footprints",
  },
  {
    id: "bloody_knife",
    name: "带血的刀",
    image_url: "",
    description: '一把厨房用的菜刀被丢弃在雪地中，刀刃上沾有血迹。刀柄上隐约刻有「王」字。',
    is_key: true,
    importance: 5,
    status: "locked" as const,
    stage: "act1_investigation",
    scene_id: "crime_scene",
    hotspot_id: "bloody_knife_spot",
  },
  {
    id: "threatening_letter",
    name: "恐吓信",
    image_url: "",
    description: '在吧台下发现一封被揉皱的信，上面写着「你逃不掉的，二十年前的账该算清了」。',
    is_key: true,
    importance: 5,
    status: "locked" as const,
    stage: "act2_investigation",
    scene_id: "restaurant_hall",
    hotspot_id: "bar_counter",
  },
  {
    id: "old_photo",
    name: "老照片",
    image_url: "",
    description: '照片墙上的一张泛黄合影，照片中的年轻人中有一人酷似王大达，但照片背面写着「1998·程」。',
    is_key: true,
    importance: 4,
    status: "locked" as const,
    stage: "act1_investigation",
    scene_id: "restaurant_hall",
    hotspot_id: "photo_wall",
  },
  {
    id: "torn_cloth_fragment",
    name: "碎布条",
    image_url: "",
    description: "现场发现的蓝色布料碎片，看起来是从某件衣服上撕下来的，边缘整齐像是被刀割破。",
    is_key: false,
    importance: 3,
    status: "locked" as const,
    stage: "act1_investigation",
    scene_id: "crime_scene",
    hotspot_id: "torn_cloth",
  },
  {
    id: "blood_type_report",
    name: "血型报告",
    image_url: "",
    description: "初步鉴证报告显示，现场血迹为O型血。王大达是A型血。",
    is_key: true,
    importance: 4,
    status: "locked" as const,
    stage: "act2_investigation",
    scene_id: "crime_scene",
    hotspot_id: "body_outline",
  },
  {
    id: "phone_record",
    name: "通话记录",
    image_url: "",
    description: "程俊的手机通话记录显示，案发当晚他曾与一个未显示号码的来电通话3分钟。",
    is_key: true,
    importance: 4,
    status: "locked" as const,
    stage: "act2_investigation",
    scene_id: "crime_scene",
    hotspot_id: "body_outline",
  },
  {
    id: "hidden_letter",
    name: "隐藏的信",
    image_url: "",
    description: "在程俊床板下发现的信：'程俊，我知道你是当年冤案的受害者。来雪乡找我，我会告诉你真相。——王'",
    is_key: true,
    importance: 5,
    status: "locked" as const,
    stage: "act2_investigation",
    scene_id: "village_entrance",
    hotspot_id: "snow_tracks",
  },
];

// ─── 证物定义 ───

export const mockEvidences = [
  {
    id: "bloody_knife_evidence",
    name: "带血的刀（证物）",
    image_url: "",
    description_surface: "一把厨房用菜刀，刀刃沾有暗红色血迹。",
    description_deep: '刀柄刻有「王」字，但磨损程度显示这把刀有二十年以上的历史。血迹经检测为O型。',
    status: "undiscovered" as const,
    can_show_to_npc: true,
    shown_to_characters: [] as string[],
  },
  {
    id: "broken_glass_evidence",
    name: "碎玻璃杯",
    image_url: "",
    description_surface: "破碎的玻璃杯碎片，边缘有暗红色物质。",
    description_deep: "玻璃杯底部有微小的刻字，似乎是某家饭店的定制酒杯。",
    status: "undiscovered" as const,
    can_show_to_npc: true,
    shown_to_characters: [] as string[],
  },
  {
    id: "threatening_letter_evidence",
    name: "恐吓信（证物）",
    image_url: "",
    description_surface: "一封被揉皱的信，字迹潦草。",
    description_deep: "信纸是本地小卖部出售的廉价信纸。字迹虽然刻意扭曲，但笔锋有练字痕迹。",
    status: "undiscovered" as const,
    can_show_to_npc: true,
    shown_to_characters: [] as string[],
  },
  {
    id: "old_photo_evidence",
    name: "老照片（证物）",
    image_url: "",
    description_surface: "一张泛黄的集体照，背面写着'1998·程'。",
    description_deep: "照片中的年轻人有六人，其中一人与王大达极为相似。照片被小心地藏在了相框夹层中。",
    status: "undiscovered" as const,
    can_show_to_npc: true,
    shown_to_characters: [] as string[],
  },
  {
    id: "torn_cloth_evidence",
    name: "碎布条（证物）",
    image_url: "",
    description_surface: "蓝色布料碎片，边缘整齐。",
    description_deep: "布料材质为户外冲锋衣常见面料，品牌标签隐约可见'SNOW'字样。",
    status: "undiscovered" as const,
    can_show_to_npc: true,
    shown_to_characters: [] as string[],
  },
];

// ─── 阶段定义 ───

export const mockStages = [
  {
    id: "prologue",
    name: "序章",
    sort_order: 0,
    available_actions: ["talk_to_npc", "open_clue_board"],
    available_characters: ["dm", "wangdada"],
    scene_id: "village_entrance",
  },
  {
    id: "act1_investigation",
    name: "第一幕·第一轮搜证",
    sort_order: 1,
    available_actions: ["talk_to_npc", "examine_scene", "show_evidence", "open_clue_board", "request_advance"],
    available_characters: ["wangdada", "chengjun"],
    scene_id: "restaurant_hall",
  },
  {
    id: "act1_event",
    name: "第一幕·事件推进",
    sort_order: 2,
    available_actions: ["talk_to_npc", "examine_scene", "open_clue_board"],
    available_characters: ["wangdada", "chengjun"],
    scene_id: "crime_scene",
  },
  {
    id: "act2_investigation",
    name: "第二幕·深入调查",
    sort_order: 3,
    available_actions: ["talk_to_npc", "examine_scene", "show_evidence", "use_card", "open_clue_board", "request_advance"],
    available_characters: ["wangdada", "chengjun"],
    scene_id: "restaurant_hall",
  },
  {
    id: "act2_confrontation",
    name: "第二幕·对峙",
    sort_order: 4,
    available_actions: ["talk_to_npc", "show_evidence", "use_card", "open_clue_board"],
    available_characters: ["wangdada", "chengjun"],
    scene_id: "back_alley",
  },
  {
    id: "act3_reveal",
    name: "最终章·真相大白",
    sort_order: 5,
    available_actions: ["talk_to_npc", "show_evidence", "open_clue_board"],
    available_characters: ["wangdada", "chengjun"],
    scene_id: "crime_scene",
  },
  {
    id: "epilogue",
    name: "尾声",
    sort_order: 6,
    available_actions: [],
    available_characters: ["dm"],
    scene_id: "village_entrance",
  },
];

// ─── 模拟对话数据 ───

export interface MockDialogResponse {
  text: string;
  emotion: string;
  state_changes: Record<string, number>;
  triggered_events: string[];
  media_triggers: Array<{ action: string; asset_id: string }>;
}

// NPC 初始对话映射
const npcDialogues: Record<string, Record<string, MockDialogResponse[]>> = {
  wangdada: {
    default: [
      {
        text: "你们可算来了！我都等半天了。快进来坐，外面冷！",
        emotion: "normal",
        state_changes: { trust: 5 },
        triggered_events: [],
        media_triggers: [],
      },
      {
        text: "啊？昨晚？我一直在厨房忙活啊，没出过门。年三十嘛，客多。",
        emotion: "slightly_nervous",
        state_changes: { trust: 0, nervous: 10 },
        triggered_events: [],
        media_triggers: [],
      },
      {
        text: "声音？没……没有啊，我睡得很早。年纪大了，耳朵不好使。",
        emotion: "nervous",
        state_changes: { trust: -5, nervous: 15 },
        triggered_events: [],
        media_triggers: [],
      },
      {
        text: "（擦汗）你问这个干嘛？那都是以前的事了……我在这村子住了二十年，能有什么事？",
        emotion: "defensive",
        state_changes: { trust: -10, nervous: 20 },
        triggered_events: [],
        media_triggers: [{ action: "play_audio", asset_id: "sfx_tension" }],
      },
    ],
  },
  chengjun: {
    default: [
      {
        text: "……（沉默地看着你）",
        emotion: "cold",
        state_changes: { trust: 0 },
        triggered_events: [],
        media_triggers: [],
      },
      {
        text: "我昨晚在山里。打猎。",
        emotion: "cold",
        state_changes: { trust: 0, suspicious: 5 },
        triggered_events: [],
        media_triggers: [],
      },
      {
        text: "我的刀？不知道。丢了好几天了。",
        emotion: "slightly_agitated",
        state_changes: { trust: -5, suspicious: 15 },
        triggered_events: [],
        media_triggers: [{ action: "play_audio", asset_id: "sfx_tension" }],
      },
    ],
  },
  dm: {
    default: [
      {
        text: "夜幕降临，雪乡的灯笼一盏盏亮了起来。温暖的灯光映照着飘落的雪花，远处传来零星的爆竹声。",
        emotion: "calm",
        state_changes: {},
        triggered_events: [],
        media_triggers: [],
      },
      {
        text: "你推开饭店的木门，一股热浪扑面而来。炉火烧得正旺，几个客人正在喝酒聊天。王大达在柜台后面擦拭着酒杯。",
        emotion: "calm",
        state_changes: {},
        triggered_events: [],
        media_triggers: [],
      },
      {
        text: "一桩离奇的命案打破了雪乡的宁静。有人在雪地中发现了一具尸体，死者身上有刀伤。",
        emotion: "serious",
        state_changes: {},
        triggered_events: [],
        media_triggers: [{ action: "play_audio", asset_id: "sfx_tension" }],
      },
    ],
  },
};

// 证物出示反应
const evidenceReactions: Record<string, Record<string, MockDialogResponse>> = {
  wangdada: {
    bloody_knife_evidence: {
      text: "这刀是我家的！但昨晚它明明在厨房里……是谁拿出去的？！",
      emotion: "shocked",
      state_changes: { shock: 20, fear: 30, trust: -15 },
      triggered_events: ["knife_reaction"],
      media_triggers: [{ action: "play_audio", asset_id: "sfx_tension" }],
    },
    threatening_letter_evidence: {
      text: "（脸色煞白）这……这封信你是从哪里找到的？！不关我的事！我什么都不知道！",
      emotion: "fear",
      state_changes: { fear: 40, trust: -20 },
      triggered_events: ["letter_reaction"],
      media_triggers: [{ action: "play_audio", asset_id: "sfx_tension" }],
    },
    old_photo_evidence: {
      text: "（手微微发抖）这张照片……你……你怎么找到的？那都是很久以前的事了。",
      emotion: "nervous",
      state_changes: { nervous: 25, trust: -10 },
      triggered_events: ["photo_reaction"],
      media_triggers: [],
    },
  },
  chengjun: {
    bloody_knife_evidence: {
      text: "（眼神闪烁）那不是我的刀。我从不进那家饭店。",
      emotion: "defensive",
      state_changes: { suspicious: 20, trust: -10 },
      triggered_events: [],
      media_triggers: [{ action: "play_audio", asset_id: "sfx_tension" }],
    },
    old_photo_evidence: {
      text: "（长久地沉默）……你竟然找到了这个。好吧，也许……是时候说出真相了。",
      emotion: "sad",
      state_changes: { trust: 30, shock: 10 },
      triggered_events: ["chengjun_confession"],
      media_triggers: [{ action: "play_audio", asset_id: "bgm_reveal" }],
    },
  },
};

// ─── 模拟引擎 ───

export class MockEngine {
  private stageIndex = 0;
  unlockedClueIds: Set<string> = new Set();
  discoveredEvidenceIds: Set<string> = new Set();
  chatHistory: any[] = [];
  evidenceShown: Record<string, string[]> = {};
  private messageCount = 0;

  constructor() {
    // 序章自动解锁一些内容
    this.unlockedClueIds.add("broken_glass");
  }

  getStage() {
    return mockStages[this.stageIndex];
  }

  getStageName() {
    return this.getStage().name;
  }

  getCurrentScene() {
    const stage = this.getStage();
    return mockScenes.find((s) => s.id === stage.scene_id) || mockScenes[0];
  }

  getUnlockedClues() {
    return mockClues.filter((c) => this.unlockedClueIds.has(c.id));
  }

  getDiscoveredEvidences() {
    return mockEvidences.filter((e) => this.discoveredEvidenceIds.has(e.id));
  }

  /** 模拟发送消息给NPC */
  sendMessage(charId: string, text: string): MockDialogResponse | null {
    this.messageCount++;

    // 记录玩家消息
    this.chatHistory.push({
      id: `msg-p${this.messageCount}`,
      role: "player",
      character_id: null,
      text,
      timestamp: new Date().toISOString(),
    });

    // 模拟DM特殊处理
    if (charId === "dm") {
      const dmResponses = npcDialogues.dm.default;
      const response = dmResponses[Math.min(this.messageCount - 1, dmResponses.length - 1)];
      this.chatHistory.push({
        id: `msg-n${this.messageCount}`,
        role: "npc",
        character_id: "dm",
        text: response.text,
        emotion: response.emotion,
        timestamp: new Date().toISOString(),
      });
      return response;
    }

    // NPC对话
    const charDialogues = npcDialogues[charId];
    if (charDialogues) {
      const responses = charDialogues.default;
      const idx = Math.min(
        this.chatHistory.filter((m: any) => m.character_id === charId && m.role === "npc").length,
        responses.length - 1
      );
      const response = responses[Math.max(0, idx)];

      this.chatHistory.push({
        id: `msg-n${this.messageCount}`,
        role: "npc",
        character_id: charId,
        text: response.text,
        emotion: response.emotion,
        timestamp: new Date().toISOString(),
      });

      // 触发线索检查
      if (text.includes("照片") || text.includes("照片墙")) {
        this.unlockedClueIds.add("old_photo");
        this.discoveredEvidenceIds.add("old_photo_evidence");
      }
      if (text.includes("脚印") || text.includes("血迹")) {
        this.unlockedClueIds.add("bloody_footprint");
      }

      return response;
    }

    return null;
  }

  /** 模拟调查场景 */
  examineScene(sceneId: string, hotspotId: string): any {
    // 根据热点触发线索发现
    const clueDiscoverMap: Record<string, string[]> = {
      broken_glass_spot: ["broken_glass"],
      blood_stain: ["bloody_footprint"],
      footprints: ["bloody_footprint"],
      body_outline: ["blood_type_report"],
      bloody_knife_spot: ["bloody_knife"],
      bar_counter: ["threatening_letter"],
      photo_wall: ["old_photo", "old_photo_evidence"],
      torn_cloth: ["torn_cloth_fragment"],
    };

    const evidenceDiscoverMap: Record<string, string[]> = {
      broken_glass_spot: ["broken_glass_evidence"],
      bloody_knife_spot: ["bloody_knife_evidence"],
      bar_counter: ["threatening_letter_evidence"],
      torn_cloth: ["torn_cloth_evidence"],
    };

    const discoveredClues: any[] = [];
    const discoveredEvidences: any[] = [];

    (clueDiscoverMap[hotspotId] || []).forEach((cid) => {
      if (!this.unlockedClueIds.has(cid)) {
        this.unlockedClueIds.add(cid);
        const clue = mockClues.find((c) => c.id === cid);
        if (clue) discoveredClues.push(clue);
      }
    });

    (evidenceDiscoverMap[hotspotId] || []).forEach((eid) => {
      if (!this.discoveredEvidenceIds.has(eid)) {
        this.discoveredEvidenceIds.add(eid);
        const ev = mockEvidences.find((e) => e.id === eid);
        if (ev) discoveredEvidences.push({ ...ev, status: "discovered" });
      }
    });

    const dmNarrations: Record<string, string> = {
      signboard: "你走近村口的招牌，积雪下露出几个字'雪乡欢迎您'。招牌的柱子上有几道深深的划痕。",
      snow_tracks: "雪地上有一串脚印延伸到村里。脚印很深，说明人走得很急。旁边还有一行较小的脚印。",
      restaurant_door: "饭店的大门虚掩着，温暖的灯光从门缝中透出。门上贴着倒福字。",
      kitchen_door: "厨房里热气腾腾，灶台上还放着未洗的碗筷。地上有几滴水渍。",
      photo_wall: "墙上挂着许多老照片，记录着雪乡这些年的变化。一张泛黄的合影引起了你的注意。",
      back_door: "后门虚掩着，门缝中透进冷风。地上有一些碎玻璃碴。",
      bar_counter: "吧台擦拭得很干净，但在角落的缝隙中你发现了一个纸团。",
      broken_glass_spot: "地上散落着玻璃杯碎片，边缘沾有暗红色物质。",
      blood_stain: "雪地上一片暗色，仔细看是血迹。血迹已经冻结，但形状不规则。",
      footprints: "清晰的脚印从后门通向小巷深处。脚印尺码较大，步伐间距不均匀。",
      body_outline: "雪地上有一个人形的凹陷，周围有警戒线。法医已完成了初步检查。",
      bloody_knife_spot: "雪地里有一把菜刀，刀刃上沾满血迹。刀柄朝上，似乎是被匆忙丢弃的。",
      torn_cloth: "雪地现场有一小块蓝色布料，边缘整齐，像是被利器割断的。",
      footprint_trail: "脚印沿着小巷一直延伸到村外的山林方向。",
    };

    return {
      type: "scene_result",
      scene_id: sceneId,
      hotspot_id: hotspotId,
      dm_narration: dmNarrations[hotspotId] || "你仔细查看了这个区域，没有发现什么特别的东西。",
      discovered_clues: discoveredClues,
      discovered_evidences: discoveredEvidences,
      media_triggers:
        discoveredClues.length > 0
          ? [{ action: "play_audio", asset_id: "sfx_discovery" }]
          : [],
    };
  }

  /** 模拟出示证物 */
  showEvidence(charId: string, evidenceId: string): any {
    const reactions = evidenceReactions[charId];
    if (reactions && reactions[evidenceId]) {
      const reaction = reactions[evidenceId];

      // 记录已出示
      if (!this.evidenceShown[evidenceId]) this.evidenceShown[evidenceId] = [];
      if (!this.evidenceShown[evidenceId].includes(charId)) {
        this.evidenceShown[evidenceId].push(charId);
      }

      return {
        type: "evidence_reaction",
        character_id: charId,
        evidence_id: evidenceId,
        ...reaction,
      };
    }

    return {
      type: "evidence_reaction",
      character_id: charId,
      evidence_id: evidenceId,
      text: "（看了看你手中的东西，面无表情）",
      emotion: "cold",
      state_changes: {},
      triggered_events: [],
      media_triggers: [],
    };
  }

  /** 模拟请求推进 */
  requestAdvance(reason: string): any {
    const currentStage = this.getStage();

    // 检查是否可以推进
    const requiredClues = mockClues.filter((c) => c.stage === currentStage.id && c.is_key);
    const foundRequired = requiredClues.filter((c) => this.unlockedClueIds.has(c.id));

    if (requiredClues.length > 0 && foundRequired.length < requiredClues.length) {
      return {
        type: "advance_denied",
        reason: "你还没有找到足够的线索。继续调查吧。",
        hint: `试试找找关键线索：${requiredClues.filter((c) => !this.unlockedClueIds.has(c.id)).map((c) => c.name).join("、")}`,
        suggested_action: "examine_scene",
        suggested_target: currentStage.scene_id,
      };
    }

    // 推进到下一阶段
    if (this.stageIndex < mockStages.length - 1) {
      const fromStage = currentStage;
      this.stageIndex++;
      const toStage = this.getStage();

      return {
        type: "stage_transition",
        from_stage: fromStage.id,
        to_stage: toStage.id,
        stage_name: toStage.name,
        transition_events: [
          { action: "play_audio", asset_id: "sfx_transition" },
          { action: "dm_narrate", text: `故事进入了新阶段：${toStage.name}` },
        ],
        new_state: {
          current_stage: toStage.id,
          stage_name: toStage.name,
          available_actions: toStage.available_actions,
          available_characters: toStage.available_characters,
          current_scene: toStage.scene_id,
        },
      };
    }

    return {
      type: "advance_denied",
      reason: "已经是最终阶段了，准备提交你的推理吧！",
      hint: "打开最终推理面板提交你的答案",
      suggested_action: "submit_final",
      suggested_target: "",
    };
  }

  /** 模拟提交最终推理 */
  submitFinal(submission: any): any {
    // 判定正确性（模拟）
    const correctSuspect = submission.suspect === "chengjun";
    const correctMotive = submission.motive === "复仇" || submission.motive === "报仇";
    const hasKeyEvidences = submission.key_evidences?.includes("bloody_knife_evidence") || false;

    const score = Math.min(
      100,
      (correctSuspect ? 40 : 0) +
        (correctMotive ? 20 : 0) +
        (hasKeyEvidences ? 20 : 0) +
        Math.floor(Math.random() * 10) +
        10
    );

    const endingId = score >= 70 ? "truth_revealed" : "partial_truth";

    return {
      type: "submission_result",
      correct: score >= 70,
      score,
      rating: score >= 90 ? "S" : score >= 70 ? "A" : score >= 50 ? "B" : "C",
      detail: {
        correct_suspect: correctSuspect,
        correct_motive: correctMotive,
        key_evidence_hit_rate: hasKeyEvidences ? "3/5" : "1/5",
        missed_key_evidences: ["hidden_letter", "phone_record"],
      },
      ending_id: endingId,
      triggered_events: [
        { action: "play_audio", asset_id: endingId === "truth_revealed" ? "bgm_reveal" : "bgm_sad" },
        { action: "dm_narrate", text: score >= 70 ? "真相，终于浮出水面……" : "有些真相，或许永远都不会被揭开。" },
      ],
    };
  }

  /** 获取复盘数据 */
  getReview(): any {
    const submission = this.submitFinal({ suspect: "chengjun", motive: "复仇", key_evidences: ["bloody_knife_evidence", "threatening_letter_evidence"] });
    return {
      session_id: "mock-session-1",
      script_id: "snow-village",
      score: submission.score,
      max_score: 100,
      rating: submission.rating,
      duration_minutes: 68,
      breakdown: {
        suspect_correct: submission.detail.correct_suspect,
        motive_correct: submission.detail.correct_motive,
        key_evidence_hit_rate: submission.detail.key_evidence_hit_rate,
        wrong_accusations: 1,
        total_clues_found: this.unlockedClueIds.size,
        total_clues_available: mockClues.length,
        clue_coverage: `${Math.round((this.unlockedClueIds.size / mockClues.length) * 100)}%`,
        hints_used: 0,
      },
      missed_key_clues: mockClues
        .filter((c) => c.is_key && !this.unlockedClueIds.has(c.id))
        .map((c) => ({ id: c.id, name: c.name, description: c.description })),
      optimal_path: ["bloody_footprint", "bloody_knife", "threatening_letter", "alibi_hole"],
      player_path: Array.from(this.unlockedClueIds),
      truth_summary:
        "程俊，原名程晓东，二十年前他的父亲被冤枉杀害了雪乡村民，含冤而死。程俊母亲含辛茹苦将他养大，临终前告诉他真相。程俊改名换姓来到雪乡，化名猎户潜伏多年。他原本想找出当年的真凶为父报仇，却意外卷入了一场新的谋杀案。真正的凶手其实是当年冤案的知情者——王大达。王大达害怕程俊发现真相，先下手为强，却误杀了另一人。雪乡的秘密，远比表面看起来更加复杂。",
    };
  }
}

// 单例
let mockEngineInstance: MockEngine | null = null;

export function getMockEngine(): MockEngine {
  if (!mockEngineInstance) {
    mockEngineInstance = new MockEngine();
  }
  return mockEngineInstance;
}

export function resetMockEngine() {
  mockEngineInstance = new MockEngine();
}
