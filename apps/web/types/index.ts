export interface ScriptPackage {
  id: string;
  title: string;
  description: string;
  poster_url?: string;
  difficulty: number;
  duration_minutes: number;
  genre: string[];
  status: "draft" | "published" | "archived";
}

export interface GameSession {
  session_id: string;
  script_id: string;
  status: "in_progress" | "paused" | "completed" | "abandoned";
  current_stage: string;
  player_character_id: string;
  available_actions: string[];
  current_scene?: string;
}

export interface Character {
  id: string;
  name: string;
  portrait_url?: string;
  playable: boolean;
  is_dm_alter_ego?: boolean;
  personality?: string;
}

export interface Clue {
  id: string;
  name: string;
  image_url?: string;
  description: string;
  is_key: boolean;
  importance: number;
  status: "locked" | "unlocked" | "discovered" | "viewed";
}

export interface Evidence {
  id: string;
  name: string;
  image_url?: string;
  description_surface: string;
  status: "undiscovered" | "discovered" | "viewed" | "deep_viewed";
  can_show_to_npc: boolean;
}

export interface Stage {
  id: string;
  name: string;
  sort_order: number;
  available_actions: string[];
  available_characters: string[];
}
