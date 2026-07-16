export interface DemoArticle {
  id: string;
  eyebrow: string;
  title: string;
  summary: string;
  readTime: string;
  content: Array<
    | { type: "paragraph"; text: string }
    | { type: "quote"; text: string }
    | { type: "note"; label: string; text: string }
  >;
}

export interface DemoPoint {
  x: number;
  y: number;
}

export interface DemoRect extends DemoPoint {
  width: number;
  height: number;
}

export interface DemoHotspot extends DemoPoint {
  id: string;
  label: string;
  articleId: string;
}

export interface DemoSessionHotspot extends DemoPoint {
  id: string;
  sceneId: string;
  label: string;
  width?: number;
  height?: number;
}

export interface DemoRoom {
  id: "west" | "hall" | "stage" | "south";
  name: string;
  bounds: DemoRect;
  label: DemoPoint;
  priority: number;
  camera: {
    padding: number;
    zoomBias: number;
    focus?: DemoPoint;
    focusWeight: number;
    lookAheadX: number;
    lookAheadY: number;
  };
}

export interface DemoWall extends DemoRect {
  id: string;
  axis: "horizontal" | "vertical";
  elevation: number;
  fadeDistance?: number;
}

export interface DemoFurniture extends DemoRect {
  id: string;
  kind: "table" | "piano" | "clock" | "statue" | "seats" | "console" | "curtain";
  elevation: number;
  sortY: number;
  rotation?: number;
  collision?: DemoRect;
  fadeDistance?: number;
  variant?: string;
}

export interface DemoDoorFrame {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  orientation: "horizontal" | "vertical";
}

export interface DemoCharacter extends DemoPoint {
  id: "player" | "linmo" | "suyin";
  name: string;
  initialFacing: "left" | "right";
  outfit: "short-coat" | "long-coat" | "soft-jacket";
  accessory: "satchel" | "keys" | "scarf";
  silhouette: {
    height: number;
    width: number;
    torsoHeight: number;
    headWidth: number;
    headHeight: number;
    shoulderRadius: number;
  };
  palette: {
    coat: string;
    trousers: string;
    skin: string;
    hair: string;
    accent: string;
  };
  motion: {
    idleSeconds: number;
    walkSeconds: number;
    delaySeconds: number;
  };
}

export const DEMO_WORLD_WIDTH = 1680;
export const DEMO_WORLD_HEIGHT = 960;

export const demoArticles: DemoArticle[] = [
  {
    id: "arrival",
    eyebrow: "人物手记 · 第一页",
    title: "一封没有寄出的信",
    summary: "纸张受过潮，墨迹在最后一句戛然而止。",
    readTime: "约 2 分钟",
    content: [
      {
        type: "paragraph",
        text: "我在傍晚六点到达旧剧场。雨水沿着铜制门环往下滴，大厅里没有人，只有舞台上的一盏工作灯还亮着。",
      },
      {
        type: "quote",
        text: "如果你看到这封信，不要相信报幕人说出的最后一个名字。",
      },
      {
        type: "paragraph",
        text: "信封里夹着半张座位表。第七排十二号被红笔圈出，但那一排座椅早在二十年前的火灾后就被拆除了。",
      },
      {
        type: "note",
        label: "边角批注",
        text: "钟声响起三次以后，去看舞台左侧的幕绳。",
      },
    ],
  },
  {
    id: "stage-note",
    eyebrow: "场务记录 · 失效页",
    title: "最后一次彩排",
    summary: "记录者反复修改了演员入场的先后顺序。",
    readTime: "约 1 分钟",
    content: [
      {
        type: "paragraph",
        text: "21:10，所有演员到场。21:17，西侧灯桥自行熄灭。21:24，有人在空置的观众席鼓掌。",
      },
      {
        type: "quote",
        text: "不要拉开主幕。幕布后面不是我们搭好的布景。",
      },
      {
        type: "paragraph",
        text: "最后一行只剩一个潦草的箭头，指向舞台中央那扇比例异常的小门。",
      },
    ],
  },
  {
    id: "portrait",
    eyebrow: "角色档案 · 02",
    title: "守门人：林默",
    summary: "他熟悉每一把钥匙，却说自己从未进入后台。",
    readTime: "档案摘录",
    content: [
      {
        type: "note",
        label: "公开身份",
        text: "旧剧场夜间看守，任职十一年。寡言，听力极好，习惯在凌晨一点巡视北侧走廊。",
      },
      {
        type: "paragraph",
        text: "林默的钥匙环上共有十九把钥匙，登记册却只记录了十八扇门。多出的那把钥匙很小，齿痕像是某种儿童玩具的配件。",
      },
      {
        type: "quote",
        text: "我没见过失踪的人。我只听见有人从墙里面叫他的名字。",
      },
    ],
  },
];

export const demoHotspots: DemoHotspot[] = [
  { id: "desk-letter", x: 428, y: 254, label: "潮湿的信件", articleId: "arrival" },
  { id: "stage-script", x: 1038, y: 446, label: "场务记录", articleId: "stage-note" },
  { id: "portrait-wall", x: 1362, y: 240, label: "褪色的肖像", articleId: "portrait" },
];

export const demoRooms: DemoRoom[] = [
  {
    id: "west",
    name: "西侧阅览室",
    bounds: { x: 74, y: 72, width: 536, height: 404 },
    label: { x: 232, y: 154 },
    priority: 2,
    camera: {
      padding: 82,
      zoomBias: 0.96,
      focus: { x: 350, y: 270 },
      focusWeight: 0.12,
      lookAheadX: 82,
      lookAheadY: 46,
    },
  },
  {
    id: "hall",
    name: "中央观众厅",
    bounds: { x: 664, y: 72, width: 504, height: 802 },
    label: { x: 836, y: 284 },
    priority: 1,
    camera: {
      padding: 90,
      zoomBias: 0.98,
      focus: { x: 916, y: 430 },
      focusWeight: 0.08,
      lookAheadX: 96,
      lookAheadY: 54,
    },
  },
  {
    id: "stage",
    name: "舞台与幕间",
    bounds: { x: 1222, y: 72, width: 384, height: 404 },
    label: { x: 1320, y: 154 },
    priority: 3,
    camera: {
      padding: 72,
      zoomBias: 1.03,
      focus: { x: 1436, y: 280 },
      focusWeight: 0.18,
      lookAheadX: 72,
      lookAheadY: 40,
    },
  },
  {
    id: "south",
    name: "南侧回廊",
    bounds: { x: 74, y: 520, width: 1532, height: 354 },
    label: { x: 748, y: 814 },
    priority: 4,
    camera: {
      padding: 86,
      zoomBias: 0.95,
      focusWeight: 0,
      lookAheadX: 112,
      lookAheadY: 40,
    },
  },
];

export const demoWalls: DemoWall[] = [
  { id: "north", x: 0, y: 0, width: DEMO_WORLD_WIDTH, height: 72, axis: "horizontal", elevation: 52 },
  { id: "south", x: 0, y: DEMO_WORLD_HEIGHT - 86, width: DEMO_WORLD_WIDTH, height: 86, axis: "horizontal", elevation: 44 },
  { id: "west", x: 0, y: 0, width: 74, height: DEMO_WORLD_HEIGHT, axis: "vertical", elevation: 44 },
  { id: "east", x: DEMO_WORLD_WIDTH - 74, y: 0, width: 74, height: DEMO_WORLD_HEIGHT, axis: "vertical", elevation: 44 },
  { id: "west-upper", x: 610, y: 72, width: 54, height: 280, axis: "vertical", elevation: 46, fadeDistance: 105 },
  { id: "west-lower", x: 610, y: 540, width: 54, height: 334, axis: "vertical", elevation: 46, fadeDistance: 105 },
  { id: "stage-upper", x: 1168, y: 72, width: 54, height: 256, axis: "vertical", elevation: 46, fadeDistance: 105 },
  { id: "stage-lower", x: 1168, y: 530, width: 54, height: 344, axis: "vertical", elevation: 46, fadeDistance: 105 },
  { id: "west-divider-a", x: 74, y: 476, width: 284, height: 44, axis: "horizontal", elevation: 42, fadeDistance: 98 },
  { id: "west-divider-b", x: 500, y: 476, width: 110, height: 44, axis: "horizontal", elevation: 42, fadeDistance: 98 },
  { id: "stage-divider-a", x: 1222, y: 476, width: 104, height: 44, axis: "horizontal", elevation: 42, fadeDistance: 98 },
  { id: "stage-divider-b", x: 1460, y: 476, width: 146, height: 44, axis: "horizontal", elevation: 42, fadeDistance: 98 },
];

export const demoFurniture: DemoFurniture[] = [
  { id: "reading-table", kind: "table", x: 350, y: 222, width: 162, height: 84, elevation: 34, sortY: 306, variant: "reading" },
  { id: "south-table", kind: "table", x: 904, y: 616, width: 170, height: 92, elevation: 36, sortY: 708, variant: "south", collision: { x: 904, y: 616, width: 170, height: 92 } },
  { id: "piano", kind: "piano", x: 126, y: 650, width: 210, height: 88, elevation: 48, sortY: 738, rotation: -5 },
  { id: "clock", kind: "clock", x: 1432, y: 604, width: 64, height: 154, elevation: 72, sortY: 758 },
  { id: "statue", kind: "statue", x: 700, y: 114, width: 70, height: 148, elevation: 72, sortY: 262 },
  { id: "seats", kind: "seats", x: 760, y: 330, width: 306, height: 166, elevation: 32, sortY: 496, rotation: -1 },
  { id: "gallery-console", kind: "console", x: 870, y: 148, width: 218, height: 68, elevation: 30, sortY: 216, collision: { x: 870, y: 148, width: 218, height: 68 } },
  { id: "curtain-left", kind: "curtain", x: 1222, y: 72, width: 154, height: 418, elevation: 70, sortY: 490, variant: "left", fadeDistance: 120 },
  { id: "curtain-right", kind: "curtain", x: 1452, y: 72, width: 154, height: 418, elevation: 70, sortY: 490, variant: "right", fadeDistance: 120 },
];

export const demoDoorFrames: DemoDoorFrame[] = [
  { id: "west-passage", x: 610, y: 352, width: 54, height: 188, orientation: "vertical" },
  { id: "stage-passage", x: 1168, y: 328, width: 54, height: 202, orientation: "vertical" },
  { id: "west-south-passage", x: 358, y: 476, width: 142, height: 44, orientation: "horizontal" },
  { id: "stage-south-passage", x: 1326, y: 476, width: 134, height: 44, orientation: "horizontal" },
];

export const demoCharacters: DemoCharacter[] = [
  {
    id: "player",
    name: "卓司元",
    x: 780,
    y: 704,
    initialFacing: "right",
    outfit: "short-coat",
    accessory: "satchel",
    silhouette: { height: 72, width: 46, torsoHeight: 46, headWidth: 19, headHeight: 21, shoulderRadius: 42 },
    palette: { coat: "#9d906f", trousers: "#252722", skin: "#aa9c7e", hair: "#262722", accent: "#c7b68a" },
    motion: { idleSeconds: 3.3, walkSeconds: 0.48, delaySeconds: -0.8 },
  },
  {
    id: "linmo",
    name: "林默",
    x: 1320,
    y: 610,
    initialFacing: "left",
    outfit: "long-coat",
    accessory: "keys",
    silhouette: { height: 83, width: 42, torsoHeight: 57, headWidth: 18, headHeight: 23, shoulderRadius: 26 },
    palette: { coat: "#56636a", trousers: "#1b2021", skin: "#918775", hair: "#171b1c", accent: "#83959e" },
    motion: { idleSeconds: 4.1, walkSeconds: 0.54, delaySeconds: -2.2 },
  },
  {
    id: "suyin",
    name: "苏吟",
    x: 320,
    y: 610,
    initialFacing: "right",
    outfit: "soft-jacket",
    accessory: "scarf",
    silhouette: { height: 67, width: 50, torsoHeight: 43, headWidth: 21, headHeight: 20, shoulderRadius: 62 },
    palette: { coat: "#73504d", trousers: "#292120", skin: "#b2a084", hair: "#302321", accent: "#aa756d" },
    motion: { idleSeconds: 3.7, walkSeconds: 0.5, delaySeconds: -1.5 },
  },
];
