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
  id: "hall" | "kitchen" | "study" | "private" | "archive";
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
  seat?: {
    position: DemoPoint;
    stand: DemoPoint;
    facing: "front" | "back" | "left" | "right";
  };
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

export const DEMO_WORLD_WIDTH = 2400;
export const DEMO_WORLD_HEIGHT = 1600;

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
  { id: "desk-letter", x: 350, y: 330, label: "潮湿的信件", articleId: "arrival" },
  { id: "stage-script", x: 350, y: 1240, label: "场务记录", articleId: "stage-note" },
  { id: "portrait-wall", x: 2050, y: 1190, label: "褪色的肖像", articleId: "portrait" },
];

export const demoRooms: DemoRoom[] = [
  {
    id: "hall",
    name: "圆桌大厅",
    bounds: { x: 720, y: 320, width: 960, height: 980 },
    label: { x: 1120, y: 390 },
    priority: 1,
    camera: {
      padding: 96,
      zoomBias: 0.98,
      focus: { x: 1200, y: 800 },
      focusWeight: 0.06,
      lookAheadX: 116,
      lookAheadY: 70,
    },
  },
  {
    id: "kitchen",
    name: "厨房",
    bounds: { x: 60, y: 60, width: 560, height: 560 },
    label: { x: 150, y: 132 },
    priority: 2,
    camera: {
      padding: 80,
      zoomBias: 1,
      focus: { x: 340, y: 340 },
      focusWeight: 0.12,
      lookAheadX: 84,
      lookAheadY: 58,
    },
  },
  {
    id: "study",
    name: "书房",
    bounds: { x: 60, y: 980, width: 560, height: 560 },
    label: { x: 150, y: 1052 },
    priority: 2,
    camera: {
      padding: 80,
      zoomBias: 1,
      focus: { x: 340, y: 1260 },
      focusWeight: 0.12,
      lookAheadX: 84,
      lookAheadY: 58,
    },
  },
  {
    id: "private",
    name: "私聊室",
    bounds: { x: 1780, y: 60, width: 560, height: 560 },
    label: { x: 1870, y: 132 },
    priority: 2,
    camera: {
      padding: 80,
      zoomBias: 1,
      focus: { x: 2060, y: 340 },
      focusWeight: 0.12,
      lookAheadX: 84,
      lookAheadY: 58,
    },
  },
  {
    id: "archive",
    name: "档案室",
    bounds: { x: 1780, y: 980, width: 560, height: 560 },
    label: { x: 1870, y: 1052 },
    priority: 2,
    camera: {
      padding: 80,
      zoomBias: 1,
      focus: { x: 2060, y: 1260 },
      focusWeight: 0.12,
      lookAheadX: 84,
      lookAheadY: 58,
    },
  },
];

export const demoWalls: DemoWall[] = [
  { id: "world-north", x: 0, y: 0, width: DEMO_WORLD_WIDTH, height: 40, axis: "horizontal", elevation: 48 },
  { id: "world-south", x: 0, y: 1560, width: DEMO_WORLD_WIDTH, height: 40, axis: "horizontal", elevation: 42 },
  { id: "world-west", x: 0, y: 0, width: 40, height: DEMO_WORLD_HEIGHT, axis: "vertical", elevation: 42 },
  { id: "world-east", x: 2360, y: 0, width: 40, height: DEMO_WORLD_HEIGHT, axis: "vertical", elevation: 42 },
  { id: "hall-north", x: 680, y: 280, width: 1040, height: 40, axis: "horizontal", elevation: 50 },
  { id: "hall-south", x: 680, y: 1300, width: 1040, height: 40, axis: "horizontal", elevation: 44 },
  { id: "hall-west-a", x: 680, y: 320, width: 40, height: 110, axis: "vertical", elevation: 46, fadeDistance: 105 },
  { id: "hall-west-b", x: 680, y: 550, width: 40, height: 550, axis: "vertical", elevation: 46, fadeDistance: 105 },
  { id: "hall-west-c", x: 680, y: 1220, width: 40, height: 80, axis: "vertical", elevation: 46, fadeDistance: 105 },
  { id: "hall-east-a", x: 1680, y: 320, width: 40, height: 110, axis: "vertical", elevation: 46, fadeDistance: 105 },
  { id: "hall-east-b", x: 1680, y: 550, width: 40, height: 550, axis: "vertical", elevation: 46, fadeDistance: 105 },
  { id: "hall-east-c", x: 1680, y: 1220, width: 40, height: 80, axis: "vertical", elevation: 46, fadeDistance: 105 },
  { id: "kitchen-north", x: 40, y: 40, width: 600, height: 40, axis: "horizontal", elevation: 44 },
  { id: "kitchen-south", x: 40, y: 620, width: 600, height: 40, axis: "horizontal", elevation: 42 },
  { id: "kitchen-west", x: 40, y: 80, width: 40, height: 540, axis: "vertical", elevation: 42 },
  { id: "kitchen-east-a", x: 600, y: 80, width: 40, height: 350, axis: "vertical", elevation: 42 },
  { id: "kitchen-east-b", x: 600, y: 550, width: 40, height: 70, axis: "vertical", elevation: 42 },
  { id: "kitchen-corridor-north", x: 640, y: 390, width: 80, height: 40, axis: "horizontal", elevation: 38 },
  { id: "kitchen-corridor-south", x: 640, y: 550, width: 80, height: 40, axis: "horizontal", elevation: 38 },
  { id: "study-north", x: 40, y: 960, width: 600, height: 40, axis: "horizontal", elevation: 42 },
  { id: "study-south", x: 40, y: 1540, width: 600, height: 40, axis: "horizontal", elevation: 42 },
  { id: "study-west", x: 40, y: 1000, width: 40, height: 540, axis: "vertical", elevation: 42 },
  { id: "study-east-a", x: 600, y: 1000, width: 40, height: 100, axis: "vertical", elevation: 42 },
  { id: "study-east-b", x: 600, y: 1220, width: 40, height: 320, axis: "vertical", elevation: 42 },
  { id: "study-corridor-north", x: 640, y: 1060, width: 80, height: 40, axis: "horizontal", elevation: 38 },
  { id: "study-corridor-south", x: 640, y: 1220, width: 80, height: 40, axis: "horizontal", elevation: 38 },
  { id: "private-north", x: 1760, y: 40, width: 600, height: 40, axis: "horizontal", elevation: 44 },
  { id: "private-south", x: 1760, y: 620, width: 600, height: 40, axis: "horizontal", elevation: 42 },
  { id: "private-east", x: 2320, y: 80, width: 40, height: 540, axis: "vertical", elevation: 42 },
  { id: "private-west-a", x: 1760, y: 80, width: 40, height: 350, axis: "vertical", elevation: 42 },
  { id: "private-west-b", x: 1760, y: 550, width: 40, height: 70, axis: "vertical", elevation: 42 },
  { id: "private-corridor-north", x: 1680, y: 390, width: 80, height: 40, axis: "horizontal", elevation: 38 },
  { id: "private-corridor-south", x: 1680, y: 550, width: 80, height: 40, axis: "horizontal", elevation: 38 },
  { id: "archive-north", x: 1760, y: 960, width: 600, height: 40, axis: "horizontal", elevation: 42 },
  { id: "archive-south", x: 1760, y: 1540, width: 600, height: 40, axis: "horizontal", elevation: 42 },
  { id: "archive-east", x: 2320, y: 1000, width: 40, height: 540, axis: "vertical", elevation: 42 },
  { id: "archive-west-a", x: 1760, y: 1000, width: 40, height: 100, axis: "vertical", elevation: 42 },
  { id: "archive-west-b", x: 1760, y: 1220, width: 40, height: 320, axis: "vertical", elevation: 42 },
  { id: "archive-corridor-north", x: 1680, y: 1060, width: 80, height: 40, axis: "horizontal", elevation: 38 },
  { id: "archive-corridor-south", x: 1680, y: 1220, width: 80, height: 40, axis: "horizontal", elevation: 38 },
];

export const demoFurniture: DemoFurniture[] = [
  { id: "round-table", kind: "table", x: 1080, y: 700, width: 240, height: 170, elevation: 42, sortY: 870, variant: "round", collision: { x: 1080, y: 700, width: 240, height: 170 } },
  { id: "chair-n", kind: "seats", x: 1171, y: 620, width: 58, height: 42, elevation: 22, sortY: 662, variant: "chair", rotation: 1, collision: { x: 1175, y: 626, width: 50, height: 32 }, seat: { position: { x: 1200, y: 664 }, stand: { x: 1200, y: 570 }, facing: "front" } },
  { id: "chair-ne", kind: "seats", x: 1338, y: 680, width: 58, height: 42, elevation: 22, sortY: 722, variant: "chair", rotation: -5, collision: { x: 1342, y: 686, width: 50, height: 32 }, seat: { position: { x: 1367, y: 724 }, stand: { x: 1455, y: 680 }, facing: "left" } },
  { id: "chair-se", kind: "seats", x: 1338, y: 900, width: 58, height: 42, elevation: 22, sortY: 942, variant: "chair", rotation: 4, collision: { x: 1342, y: 906, width: 50, height: 32 }, seat: { position: { x: 1367, y: 944 }, stand: { x: 1455, y: 970 }, facing: "left" } },
  { id: "chair-s", kind: "seats", x: 1171, y: 910, width: 58, height: 42, elevation: 22, sortY: 952, variant: "chair", rotation: -2, collision: { x: 1175, y: 916, width: 50, height: 32 }, seat: { position: { x: 1200, y: 954 }, stand: { x: 1200, y: 1050 }, facing: "back" } },
  { id: "chair-sw", kind: "seats", x: 1004, y: 900, width: 58, height: 42, elevation: 22, sortY: 942, variant: "chair", rotation: -4, collision: { x: 1008, y: 906, width: 50, height: 32 }, seat: { position: { x: 1033, y: 944 }, stand: { x: 945, y: 970 }, facing: "right" } },
  { id: "chair-nw", kind: "seats", x: 1004, y: 680, width: 58, height: 42, elevation: 22, sortY: 722, variant: "chair", rotation: 5, collision: { x: 1008, y: 686, width: 50, height: 32 }, seat: { position: { x: 1033, y: 724 }, stand: { x: 945, y: 680 }, facing: "right" } },
  { id: "hall-console", kind: "console", x: 1450, y: 1150, width: 170, height: 64, elevation: 30, sortY: 1214, rotation: 3 },
  { id: "kitchen-counter", kind: "console", x: 120, y: 150, width: 340, height: 82, elevation: 34, sortY: 232, collision: { x: 120, y: 150, width: 340, height: 82 } },
  { id: "kitchen-table", kind: "table", x: 250, y: 390, width: 160, height: 104, elevation: 32, sortY: 494, rotation: -4, collision: { x: 250, y: 390, width: 160, height: 104 } },
  { id: "kitchen-clock", kind: "clock", x: 510, y: 330, width: 60, height: 146, elevation: 64, sortY: 476 },
  { id: "study-shelf", kind: "console", x: 110, y: 1060, width: 92, height: 330, elevation: 46, sortY: 1390, collision: { x: 110, y: 1060, width: 92, height: 330 } },
  { id: "study-desk", kind: "table", x: 300, y: 1230, width: 190, height: 112, elevation: 34, sortY: 1342, rotation: 4, collision: { x: 300, y: 1230, width: 190, height: 112 } },
  { id: "study-piano", kind: "piano", x: 270, y: 1430, width: 220, height: 82, elevation: 44, sortY: 1512, rotation: -3 },
  { id: "private-seats", kind: "seats", x: 1900, y: 250, width: 300, height: 150, elevation: 34, sortY: 400, variant: "private", rotation: -2 },
  { id: "private-console", kind: "console", x: 2000, y: 470, width: 220, height: 64, elevation: 28, sortY: 534, rotation: 2 },
  { id: "archive-cabinets", kind: "console", x: 1870, y: 1060, width: 350, height: 92, elevation: 44, sortY: 1152, collision: { x: 1870, y: 1060, width: 350, height: 92 } },
  { id: "archive-table", kind: "table", x: 1970, y: 1290, width: 190, height: 112, elevation: 34, sortY: 1402, rotation: -3, collision: { x: 1970, y: 1290, width: 190, height: 112 } },
  { id: "archive-clock", kind: "clock", x: 2240, y: 1300, width: 60, height: 146, elevation: 64, sortY: 1446 },
];

export const demoDoorFrames: DemoDoorFrame[] = [
  { id: "kitchen-door", x: 680, y: 430, width: 40, height: 120, orientation: "vertical" },
  { id: "study-door", x: 680, y: 1100, width: 40, height: 120, orientation: "vertical" },
  { id: "private-door", x: 1680, y: 430, width: 40, height: 120, orientation: "vertical" },
  { id: "archive-door", x: 1680, y: 1100, width: 40, height: 120, orientation: "vertical" },
];

export const demoCharacters: DemoCharacter[] = [
  {
    id: "player",
    name: "卓司元",
    x: 1200,
    y: 1120,
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
    x: 1380,
    y: 820,
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
    x: 1020,
    y: 820,
    initialFacing: "right",
    outfit: "soft-jacket",
    accessory: "scarf",
    silhouette: { height: 67, width: 50, torsoHeight: 43, headWidth: 21, headHeight: 20, shoulderRadius: 62 },
    palette: { coat: "#73504d", trousers: "#292120", skin: "#b2a084", hair: "#302321", accent: "#aa756d" },
    motion: { idleSeconds: 3.7, walkSeconds: 0.5, delaySeconds: -1.5 },
  },
];
