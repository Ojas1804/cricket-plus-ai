export interface BatterLine { player: string; runs: number; balls: number; fours: number; sixes: number; strike_rate: number | null; on_strike: boolean; dismissal: string | null }
export interface BowlerLine { player: string; overs: string; maidens: number; runs: number; wickets: number; economy: number | null }
export interface OverSummary { over: number; balls: string[]; runs: number }
export interface InningsScore {
  number: number; team: string; runs: number; wickets: number; overs: string; legal_balls: number; completed: boolean
  batting: BatterLine[]; bowling: BowlerLine[]; fall_of_wickets: string[]; did_not_bat: string[]
}
export interface LiveMatchData {
  match_id: string; title: string; format: string; status: 'UPCOMING' | 'LIVE' | 'COMPLETED'; status_text: string
  teams: string[]; venue: string | null; current_innings: number | null; innings: InningsScore[]
  current_run_rate: number | null; required_run_rate: number | null; target: number | null
  runs_required: number | null; balls_remaining: number | null
  partnership: { runs: number; balls: number; batters: string[] } | null
  recent_overs: OverSummary[]; stale?: boolean
}
