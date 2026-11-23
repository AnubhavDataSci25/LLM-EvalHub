/**
 * Reasoning Arena: Chess
 *
 * A game-based reasoning benchmark measuring how well LLMs reason about chess
 * positions and play chess using objective ground-truth rules and engine analysis.
 *
 * Framing Notice: Chess skill is one signal for game-reasoning ability and does
 * not prove general model reasoning.
 */

import { motion } from 'framer-motion'
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock,
  Cpu,
  Eye,
  Flame,
  HelpCircle,
  History,
  Info,
  Layers,
  MessageSquare,
  Play,
  RotateCcw,
  Scale,
  Shield,
  ShieldAlert,
  Swords,
  Trophy,
  XCircle,
  Zap,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import ChessBoard from '../components/arena/ChessBoard'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  InlineNote,
  Input,
  LoadingState,
  Modal,
  PageHeader,
  Select,
  StatusBadge,
  Tabs,
  Toggle,
  useToast,
} from '../components/ui'
import { useApi } from '../hooks'
import { api } from '../lib/api'

const TABS = [
  { id: 'overview', label: 'Overview & Benchmark', icon: BookOpen },
  { id: 'arena', label: 'Interactive Arena', icon: Swords },
  { id: 'history', label: 'Run History', icon: History },
  { id: 'failures', label: 'Failure Analysis', icon: Activity },
]

const PROMPT_VARIANTS = [
  { value: 'fen_ascii', label: 'FEN + ASCII Board (Recommended)' },
  { value: 'fen_only', label: 'FEN only (Minimal)' },
  { value: 'fen_legal_moves', label: 'FEN + Legal moves list' },
  { value: 'fen_ascii_legal', label: 'FEN + ASCII Board + Legal moves' },
]

export default function ReasoningArena() {
  const [activeTab, setActiveTab] = useState('overview')
  const { notify } = useToast()
  const navigate = useNavigate()

  // Arena & Engine Status
  const {
    data: status,
    loading: statusLoading,
    reload: reloadStatus,
  } = useApi(() => api.arenaChessStatus(), [])

  // Summary statistics
  const {
    data: summary,
    loading: summaryLoading,
    reload: reloadSummary,
  } = useApi(() => api.arenaChessSummary(), [])

  // Run history
  const {
    data: runs,
    loading: runsLoading,
    reload: reloadRuns,
  } = useApi(() => api.arenaChessRuns({ limit: 50 }), [])

  // Models list
  const { data: modelsData } = useApi(() => api.providers(), [])
  const availableModels = (modelsData?.providers || []).flatMap((p) =>
    (p.models || []).map((m) => ({
      value: m.id,
      label: `${m.label || m.id} (${p.display_name || p.key})`,
      provider: p.key,
    })),
  )

  // Arena form configuration
  const [selectedModel, setSelectedModel] = useState('mock-chess-legal')
  const [selectedProvider, setSelectedProvider] = useState('mock')
  const [modelColor, setModelColor] = useState('white')
  const [promptVariant, setPromptVariant] = useState('fen_ascii')
  const [thinkStepByStep, setThinkStepByStep] = useState(false)
  const [maxMoves, setMaxMoves] = useState(40)
  const [maxRetries, setMaxRetries] = useState(1)
  const [temperature, setTemperature] = useState(0.0)

  // Execution states
  const [isRunning, setIsRunning] = useState(false)
  const [currentRun, setCurrentRun] = useState(null)
  const [selectedPly, setSelectedPly] = useState(0)

  // Dry run modal
  const [dryRunEstimate, setDryRunEstimate] = useState(null)
  const [dryRunModalOpen, setDryRunModalOpen] = useState(false)

  // Thoughts drawer
  const [inspectedMove, setInspectedMove] = useState(null)

  // Synchronise selected run from history or live
  useEffect(() => {
    if (!currentRun && runs && runs.length > 0) {
      setCurrentRun(runs[0])
      setSelectedPly(runs[0].moves?.length || 0)
    }
  }, [runs, currentRun])

  // Compute live board state from current ply in selected run
  const activeMoves = currentRun?.moves || []
  const displayedMove =
    selectedPly > 0 && selectedPly <= activeMoves.length ? activeMoves[selectedPly - 1] : null
  const currentFen =
    displayedMove?.fen_after ||
    (selectedPly === 0 ? 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1' : activeMoves[activeMoves.length - 1]?.fen_after)

  const highlightSquares = displayedMove?.parsed_move
    ? [displayedMove.parsed_move.slice(-2)]
    : []

  async function handleDryRun() {
    try {
      const estimate = await api.arenaChessDryRun({
        model_id: selectedModel,
        provider_key: selectedProvider,
        task_type: 'game',
        model_color: modelColor,
        prompt_variant: promptVariant,
        think_step_by_step: thinkStepByStep,
        max_moves: parseInt(maxMoves, 10),
        max_retries: parseInt(maxRetries, 10),
        dry_run: true,
      })
      setDryRunEstimate(estimate)
      setDryRunModalOpen(true)
    } catch (err) {
      notify({ tone: 'danger', message: `Dry run estimation failed: ${err.message}` })
    }
  }

  async function handleStartGame() {
    setIsRunning(true)
    try {
      const run = await api.createArenaChessRun({
        model_id: selectedModel,
        provider_key: selectedProvider,
        task_type: 'game',
        model_color: modelColor,
        prompt_variant: promptVariant,
        think_step_by_step: thinkStepByStep,
        temperature: parseFloat(temperature),
        max_moves: parseInt(maxMoves, 10),
        max_retries: parseInt(maxRetries, 10),
        dry_run: false,
      })
      setCurrentRun(run)
      setSelectedPly(run.moves?.length || 0)
      setActiveTab('arena')
      notify({ tone: 'success', message: 'Arena game executed successfully.' })
      reloadRuns()
      reloadSummary()
    } catch (err) {
      notify({ tone: 'danger', message: `Failed executing arena game: ${err.message}` })
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        eyebrow="Objective Game-Based Reasoning"
        title="Reasoning Arena: Chess"
        description="Benchmark LLM spatial and multi-step reasoning against objective chess rules and Stockfish evaluation."
        actions={
          <div className="flex items-center gap-2">
            <Link to="/evaluations/new?pack=chess_reasoning" className="btn-secondary flex items-center gap-1.5 text-xs">
              <Play className="h-3.5 w-3.5" />
              Run 76-Puzzle Suite
            </Link>
            <Button
              tone="primary"
              size="sm"
              icon={Swords}
              onClick={() => {
                setActiveTab('arena')
              }}
            >
              Play Arena Game
            </Button>
          </div>
        }
      />

      {/* Honest Framing Disclaimer Banner */}
      <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-xs text-ink shadow-sm">
        <div className="flex items-start gap-2.5">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <div className="space-y-1">
            <div className="font-semibold text-amber-900 dark:text-amber-200">
              Evaluation Methodology & Honesty Notice
            </div>
            <p className="leading-relaxed text-amber-800/90 dark:text-amber-300/90">
              This module provides an objective, deterministic benchmark of how well models adhere to spatial
              chess rules and solve tactical positions. <strong>Chess skill is one specific signal</strong> for game-based
              reasoning and <strong>does not prove general reasoning ability</strong>. LLM-EvalHub does not compute fake Elo
              ratings or declare any model as &quot;best at reasoning&quot;.
            </p>
          </div>
        </div>
      </div>

      {/* Engine Status Banner */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/70 bg-surface px-4 py-3 text-xs shadow-card">
        <div className="flex items-center gap-2.5">
          <Cpu className="h-4 w-4 text-accent" />
          <span className="font-medium text-ink">Engine Integration:</span>
          {statusLoading ? (
            <span className="text-muted">Detecting Stockfish...</span>
          ) : status?.stockfish_available ? (
            <Badge tone="success" icon={CheckCircle2}>
              {status.stockfish_version || 'Stockfish Active'}
            </Badge>
          ) : (
            <Badge tone="neutral" icon={Info}>
              Stockfish not installed (Rule verification active; engine metrics disabled)
            </Badge>
          )}
        </div>
        <div className="text-muted">
          Default bounds: Depth {status?.default_config?.depth || 10} · Skill {status?.default_config?.skill_level || 5} · Max {status?.default_config?.max_moves || 60} moves
        </div>
      </div>

      {/* Navigation Tabs */}
      <Tabs tabs={TABS} active={activeTab} onChange={setActiveTab} />

      {/* TAB 1: OVERVIEW & BENCHMARK */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Summary Metric Cards */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Card className="p-4">
              <div className="text-xs text-muted">Completed Runs</div>
              <div className="mt-1 font-serif text-2xl font-semibold text-ink">
                {summary?.completed_games || 0}
              </div>
              <div className="mt-1 text-[11px] text-muted">
                {summary?.total_runs || 0} total attempts
              </div>
            </Card>

            <Card className="p-4">
              <div className="text-xs text-muted">Model Wins / Draws</div>
              <div className="mt-1 font-serif text-2xl font-semibold text-accent">
                {summary?.model_wins || 0}{' '}
                <span className="text-sm font-normal text-muted">/ {summary?.draws || 0}</span>
              </div>
              <div className="mt-1 text-[11px] text-muted">
                {summary?.engine_wins || 0} engine wins · {summary?.forfeits || 0} forfeits
              </div>
            </Card>

            <Card className="p-4">
              <div className="text-xs text-muted">Avg Legal Move Rate</div>
              <div className="mt-1 font-serif text-2xl font-semibold text-ink">
                {summary?.overall_legal_move_rate !== null && summary?.overall_legal_move_rate !== undefined
                  ? `${Math.round(summary.overall_legal_move_rate * 100)}%`
                  : 'N/A'}
              </div>
              <div className="mt-1 text-[11px] text-muted">Primary rule-following floor</div>
            </Card>

            <Card className="p-4">
              <div className="text-xs text-muted">Models Evaluated</div>
              <div className="mt-1 font-serif text-2xl font-semibold text-ink">
                {summary?.models_evaluated?.length || 0}
              </div>
              <div className="mt-1 truncate text-[11px] text-muted">
                {summary?.models_evaluated?.slice(0, 2).join(', ') || 'None yet'}
              </div>
            </Card>
          </div>

          {/* Benchmark Pack Card */}
          <Card className="p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <Badge tone="accent" icon={BookOpen}>
                    Benchmark Pack #7
                  </Badge>
                  <h3 className="font-serif text-lg font-semibold text-ink">
                    Chess Reasoning Suite
                  </h3>
                </div>
                <p className="max-w-2xl text-xs text-muted leading-relaxed">
                  76 programmatically verified chess positions sourced from public-domain legal games and tactical puzzles.
                  Includes Mate-in-1, Mate-in-2, Forks, Pins, and Endgames. Evaluates legal move compliance, format compliance,
                  and tactical puzzle accuracy without requiring an LLM judge.
                </p>
              </div>

              <Link
                to="/evaluations/new?pack=chess_reasoning"
                className="btn-primary flex items-center gap-2 shrink-0 text-xs"
              >
                <Play className="h-4 w-4" />
                Evaluate Pack with Model
              </Link>
            </div>

            <div className="mt-6 grid grid-cols-2 gap-3 border-t border-border/70 pt-4 text-xs sm:grid-cols-4">
              <div>
                <span className="text-muted">Positions:</span>{' '}
                <strong className="text-ink">76 test cases</strong>
              </div>
              <div>
                <span className="text-muted">Themes:</span>{' '}
                <strong className="text-ink">mateIn1, mateIn2, fork, pin, endgame</strong>
              </div>
              <div>
                <span className="text-muted">License:</span>{' '}
                <strong className="text-ink">Creative Commons Zero (CC0)</strong>
              </div>
              <div>
                <span className="text-muted">Judge Required:</span>{' '}
                <strong className="text-ink">None (Rule engine ground truth)</strong>
              </div>
            </div>
          </Card>

          {/* Task Types Explanation */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <Card className="p-4 space-y-2">
              <div className="flex items-center gap-2 text-ink font-semibold text-sm">
                <CheckCircle2 className="h-4 w-4 text-accent" />
                1. Legal-Move Baseline
              </div>
              <p className="text-xs text-muted leading-relaxed">
                Tests basic rule following. Given a FEN position, does the model generate a legal move in
                the correct SAN or UCI format, or does it hallucinate pieces or illegal coordinates?
              </p>
            </Card>

            <Card className="p-4 space-y-2">
              <div className="flex items-center gap-2 text-ink font-semibold text-sm">
                <Zap className="h-4 w-4 text-accent" />
                2. Tactical Puzzle Suite
              </div>
              <p className="text-xs text-muted leading-relaxed">
                Given positions with known best solutions (e.g. forced checkmate or material win),
                evaluates whether the model identifies the winning continuation.
              </p>
            </Card>

            <Card className="p-4 space-y-2">
              <div className="flex items-center gap-2 text-ink font-semibold text-sm">
                <Swords className="h-4 w-4 text-accent" />
                3. Interactive Game Mode
              </div>
              <p className="text-xs text-muted leading-relaxed">
                Plays a bounded game against an engine at configured difficulty. Tracks move legality,
                centipawn loss, blunders, and retry recovery behavior.
              </p>
            </Card>
          </div>
        </div>
      )}

      {/* TAB 2: INTERACTIVE ARENA */}
      {activeTab === 'arena' && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Left Column: Board and Scrubber */}
          <div className="flex flex-col items-center gap-4 lg:col-span-5">
            <ChessBoard
              fen={currentFen}
              highlightSquares={highlightSquares}
              currentPly={selectedPly}
              maxPly={activeMoves.length}
              onPlyChange={setSelectedPly}
            />

            <div className="w-full max-w-sm rounded-xl border border-border/80 bg-surface p-3 text-xs shadow-sm">
              <div className="flex items-center justify-between text-muted">
                <span>Active FEN:</span>
                <span className="font-mono text-[10px] text-ink">{currentFen.split(' ')[1] === 'w' ? 'White to move' : 'Black to move'}</span>
              </div>
              <p className="mt-1 font-mono text-[11px] text-ink/80 break-all bg-base p-1.5 rounded-lg border border-border/60">
                {currentFen}
              </p>
            </div>
          </div>

          {/* Right Column: Run Config & Live Move Table */}
          <div className="space-y-4 lg:col-span-7">
            {/* Run Configuration Accordion / Card */}
            <Card className="p-4 space-y-4">
              <div className="flex items-center justify-between border-b border-border/60 pb-3">
                <h3 className="font-serif text-sm font-semibold text-ink flex items-center gap-2">
                  <Swords className="h-4 w-4 text-accent" />
                  Arena Game Configuration
                </h3>
                <span className="text-[11px] text-muted">Bounded quota execution</span>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field label="Model to Test">
                  <select
                    value={selectedModel}
                    onChange={(e) => {
                      const val = e.target.value
                      setSelectedModel(val)
                      const found = availableModels.find((m) => m.value === val)
                      if (found) setSelectedProvider(found.provider)
                    }}
                    className="input w-full text-xs"
                  >
                    <option value="mock-chess-legal">Mock - Chess (Strictly Legal)</option>
                    <option value="mock-chess-illegal">Mock - Chess (Simulates Illegal)</option>
                    <option value="mock-chess-unparseable">Mock - Chess (Unparseable Format)</option>
                    <option value="mock-chess-blunder">Mock - Chess (Blunder Plays)</option>
                    <option value="mock-chess-verbose">Mock - Chess (Step-by-step Reasoning)</option>
                    {availableModels.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </Field>

                <Field label="Prompt Representation">
                  <select
                    value={promptVariant}
                    onChange={(e) => setPromptVariant(e.target.value)}
                    className="input w-full text-xs"
                  >
                    {PROMPT_VARIANTS.map((v) => (
                      <option key={v.value} value={v.value}>
                        {v.label}
                      </option>
                    ))}
                  </select>
                </Field>

                <Field label="Model Color">
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setModelColor('white')}
                      className={`flex-1 rounded-xl border py-1.5 text-xs font-medium transition-colors ${
                        modelColor === 'white'
                          ? 'border-accent bg-accent text-accent-ink'
                          : 'border-border bg-base text-muted'
                      }`}
                    >
                      White (First move)
                    </button>
                    <button
                      type="button"
                      onClick={() => setModelColor('black')}
                      className={`flex-1 rounded-xl border py-1.5 text-xs font-medium transition-colors ${
                        modelColor === 'black'
                          ? 'border-accent bg-accent text-accent-ink'
                          : 'border-border bg-base text-muted'
                      }`}
                    >
                      Black (Second move)
                    </button>
                  </div>
                </Field>

                <Field label="Max Moves & Retries">
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      min="1"
                      max="100"
                      value={maxMoves}
                      onChange={(e) => setMaxMoves(e.target.value)}
                      className="text-xs"
                      title="Max moves per game"
                    />
                    <span className="text-muted text-[11px]">moves</span>
                    <Input
                      type="number"
                      min="0"
                      max="3"
                      value={maxRetries}
                      onChange={(e) => setMaxRetries(e.target.value)}
                      className="text-xs w-20"
                      title="Max retries per illegal move"
                    />
                    <span className="text-muted text-[11px]">retry</span>
                  </div>
                </Field>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                <Toggle
                  label="Think step by step"
                  description="Instructs model to analyze threats before outputting final move"
                  checked={thinkStepByStep}
                  onChange={setThinkStepByStep}
                />

                <div className="flex items-center gap-2">
                  <Button
                    tone="secondary"
                    size="sm"
                    icon={Scale}
                    onClick={handleDryRun}
                    disabled={isRunning}
                  >
                    Dry Run Estimate
                  </Button>
                  <Button
                    tone="primary"
                    size="sm"
                    icon={Play}
                    onClick={handleStartGame}
                    disabled={isRunning}
                  >
                    {isRunning ? 'Playing Game...' : 'Start Arena Game'}
                  </Button>
                </div>
              </div>
            </Card>

            {/* Current Game Summary / Live Status */}
            {currentRun && (
              <Card className="p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-2.5 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-ink">{currentRun.model_id}</span>
                    <span className="text-muted">vs</span>
                    <span className="font-semibold text-ink">Engine Opponent</span>
                    <Badge tone={currentRun.summary?.outcome === 'model_win' ? 'success' : currentRun.summary?.outcome === 'model_forfeit_illegal' ? 'danger' : 'neutral'}>
                      {currentRun.summary?.outcome || currentRun.status}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3 text-muted">
                    <span>Termination: <strong>{currentRun.summary?.termination_reason || 'In progress'}</strong></span>
                  </div>
                </div>

                {/* Game Metric Gauges */}
                <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                  <div className="bg-base p-2 rounded-lg border border-border/60">
                    <div className="text-muted text-[10px]">Legal Move Rate</div>
                    <div className="font-serif font-semibold text-ink">
                      {currentRun.summary?.legal_move_rate !== undefined
                        ? `${Math.round(currentRun.summary.legal_move_rate * 100)}%`
                        : 'N/A'}
                    </div>
                  </div>
                  <div className="bg-base p-2 rounded-lg border border-border/60">
                    <div className="text-muted text-[10px]">Format Compliance</div>
                    <div className="font-serif font-semibold text-ink">
                      {currentRun.summary?.format_compliance_rate !== undefined
                        ? `${Math.round(currentRun.summary.format_compliance_rate * 100)}%`
                        : 'N/A'}
                    </div>
                  </div>
                  <div className="bg-base p-2 rounded-lg border border-border/60">
                    <div className="text-muted text-[10px]">Avg Centipawn Loss</div>
                    <div className="font-serif font-semibold text-ink">
                      {currentRun.summary?.avg_centipawn_loss !== null && currentRun.summary?.avg_centipawn_loss !== undefined
                        ? `${currentRun.summary.avg_centipawn_loss} cp`
                        : 'Unavailable'}
                    </div>
                  </div>
                  <div className="bg-base p-2 rounded-lg border border-border/60">
                    <div className="text-muted text-[10px]">Blunder Rate</div>
                    <div className="font-serif font-semibold text-ink">
                      {currentRun.summary?.blunder_rate !== null && currentRun.summary?.blunder_rate !== undefined
                        ? `${Math.round(currentRun.summary.blunder_rate * 100)}%`
                        : 'Unavailable'}
                    </div>
                  </div>
                </div>

                {/* Move List Table */}
                <div className="overflow-x-auto max-h-60 overflow-y-auto rounded-lg border border-border/70">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-base text-muted sticky top-0 border-b border-border/70">
                      <tr>
                        <th className="py-1.5 px-2.5 font-medium">Ply</th>
                        <th className="py-1.5 px-2.5 font-medium">Player</th>
                        <th className="py-1.5 px-2.5 font-medium">Move</th>
                        <th className="py-1.5 px-2.5 font-medium">Legality</th>
                        <th className="py-1.5 px-2.5 font-medium">CP Loss</th>
                        <th className="py-1.5 px-2.5 font-medium">Latency</th>
                        <th className="py-1.5 px-2.5 font-medium text-right">Inspect</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {activeMoves.map((m) => {
                        const isSelected = selectedPly === m.ply
                        return (
                          <tr
                            key={`move-${m.ply}`}
                            onClick={() => setSelectedPly(m.ply)}
                            className={`cursor-pointer transition-colors ${
                              isSelected ? 'bg-accent/15' : 'hover:bg-base'
                            }`}
                          >
                            <td className="py-1.5 px-2.5 font-mono text-[11px] text-muted">
                              {m.ply}
                            </td>
                            <td className="py-1.5 px-2.5 capitalize text-ink">
                              {m.turn}
                            </td>
                            <td className="py-1.5 px-2.5 font-bold font-mono text-ink">
                              {m.parsed_move || '—'}
                            </td>
                            <td className="py-1.5 px-2.5">
                              {m.is_legal ? (
                                <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 dark:text-emerald-400 font-medium">
                                  <CheckCircle2 className="h-3 w-3" /> Legal
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 text-[11px] text-rose-700 dark:text-rose-400 font-medium">
                                  <XCircle className="h-3 w-3" /> Illegal
                                </span>
                              )}
                            </td>
                            <td className="py-1.5 px-2.5 text-muted">
                              {m.centipawn_loss !== null && m.centipawn_loss !== undefined
                                ? `${Math.round(m.centipawn_loss)} cp`
                                : '—'}
                              {m.is_blunder && (
                                <span className="ml-1 text-[10px] text-rose-600 font-bold">
                                  (Blunder)
                                </span>
                              )}
                            </td>
                            <td className="py-1.5 px-2.5 text-muted">
                              {m.latency_ms ? `${Math.round(m.latency_ms)} ms` : '—'}
                            </td>
                            <td className="py-1.5 px-2.5 text-right">
                              {m.raw_model_output && (
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    setInspectedMove(m)
                                  }}
                                  className="text-muted hover:text-ink p-1 rounded hover:bg-surface"
                                  title="Inspect Model Output"
                                >
                                  <Eye className="h-3.5 w-3.5" />
                                </button>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: RUN HISTORY */}
      {activeTab === 'history' && (
        <Card className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-base text-muted border-b border-border/70">
                <tr>
                  <th className="py-2.5 px-4 font-medium">Run ID</th>
                  <th className="py-2.5 px-4 font-medium">Model</th>
                  <th className="py-2.5 px-4 font-medium">Color</th>
                  <th className="py-2.5 px-4 font-medium">Outcome</th>
                  <th className="py-2.5 px-4 font-medium">Plies</th>
                  <th className="py-2.5 px-4 font-medium">Legal Move %</th>
                  <th className="py-2.5 px-4 font-medium">Date</th>
                  <th className="py-2.5 px-4 font-medium text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {runsLoading ? (
                  <tr>
                    <td colSpan="8" className="p-4 text-center text-muted">
                      Loading history...
                    </td>
                  </tr>
                ) : !runs || runs.length === 0 ? (
                  <tr>
                    <td colSpan="8" className="p-8 text-center text-muted">
                      No arena games recorded yet. Start a game in the Interactive Arena tab.
                    </td>
                  </tr>
                ) : (
                  runs.map((r) => (
                    <tr key={r.id} className="hover:bg-base/70 transition-colors">
                      <td className="py-2.5 px-4 font-mono text-[11px] text-muted">{r.id.slice(0, 12)}</td>
                      <td className="py-2.5 px-4 font-medium text-ink">{r.model_id}</td>
                      <td className="py-2.5 px-4 capitalize text-muted">{r.config?.model_color || 'white'}</td>
                      <td className="py-2.5 px-4">
                        <Badge tone={r.summary?.outcome === 'model_win' ? 'success' : r.summary?.outcome === 'model_forfeit_illegal' ? 'danger' : 'neutral'}>
                          {r.summary?.outcome || r.status}
                        </Badge>
                      </td>
                      <td className="py-2.5 px-4 text-muted">{r.summary?.total_plies || r.moves?.length || 0}</td>
                      <td className="py-2.5 px-4 font-medium text-ink">
                        {r.summary?.legal_move_rate !== undefined
                          ? `${Math.round(r.summary.legal_move_rate * 100)}%`
                          : '—'}
                      </td>
                      <td className="py-2.5 px-4 text-muted">
                        {r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}
                      </td>
                      <td className="py-2.5 px-4 text-right">
                        <Button
                          tone="secondary"
                          size="sm"
                          icon={Eye}
                          onClick={() => {
                            setCurrentRun(r)
                            setSelectedPly(r.moves?.length || 0)
                            setActiveTab('arena')
                          }}
                        >
                          View Board
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* TAB 4: FAILURE ANALYSIS */}
      {activeTab === 'failures' && (
        <div className="space-y-4">
          <Card className="p-4 space-y-2">
            <h3 className="font-serif text-base font-semibold text-ink">
              Reasoning Failure Taxonomy
            </h3>
            <p className="text-xs text-muted leading-relaxed">
              In game-based reasoning benchmarks, failures are categorized into discrete failure classes rather
              than generic hallucinations. Each class provides actionable prompt and configuration remediations.
            </p>
          </Card>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Card className="p-4 space-y-2 border-l-4 border-l-rose-500">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-ink text-sm">illegal_move</span>
                <Badge tone="danger">Rule Violation</Badge>
              </div>
              <p className="text-xs text-muted">
                The model generated a move that violates the rules of chess in the given position (e.g. moving a piece
                through blockers, moving into check, or inventing coordinates).
              </p>
              <div className="rounded-lg bg-base p-2.5 text-[11px] text-ink/90 border border-border/60">
                <strong>Remediation:</strong> Switch prompt variant from FEN-only to <code>fen_ascii_legal</code> (provide
                ASCII board and explicit list of legal moves to ground spatial reasoning).
              </div>
            </Card>

            <Card className="p-4 space-y-2 border-l-4 border-l-amber-500">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-ink text-sm">unparseable_move</span>
                <Badge tone="warning">Format Error</Badge>
              </div>
              <p className="text-xs text-muted">
                The model returned unstructured commentary or ambiguous notation with no parseable SAN or UCI token.
              </p>
              <div className="rounded-lg bg-base p-2.5 text-[11px] text-ink/90 border border-border/60">
                <strong>Remediation:</strong> Strengthen prompt output constraint to explicitly mandate <code>&apos;Final Move: &lt;move&gt;&apos;</code> on its own line.
              </div>
            </Card>

            <Card className="p-4 space-y-2 border-l-4 border-l-purple-500">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-ink text-sm">wrong_color_or_turn_confusion</span>
                <Badge tone="neutral">Color Confusion</Badge>
              </div>
              <p className="text-xs text-muted">
                The move is strictly legal for the opponent, indicating the model lost track of which color it is playing.
              </p>
              <div className="rounded-lg bg-base p-2.5 text-[11px] text-ink/90 border border-border/60">
                <strong>Remediation:</strong> State the active player color in both the opening sentence and immediately
                preceding the output instruction.
              </div>
            </Card>

            <Card className="p-4 space-y-2 border-l-4 border-l-blue-500">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-ink text-sm">blunder</span>
                <Badge tone="neutral">Tactical Drop</Badge>
              </div>
              <p className="text-xs text-muted">
                The move was legal, but incurred a centipawn loss &gt; 300 against engine evaluation.
              </p>
              <div className="rounded-lg bg-base p-2.5 text-[11px] text-ink/90 border border-border/60">
                <strong>Remediation:</strong> Enable &quot;Think step by step&quot; or test models with higher reasoning benchmarks.
              </div>
            </Card>
          </div>
        </div>
      )}

      {/* Dry Run Estimate Modal */}
      <Modal
        open={dryRunModalOpen}
        onClose={() => setDryRunModalOpen(false)}
        title="Dry Run Quota Estimate"
        description="Verify anticipated API calls before starting game execution."
      >
        {dryRunEstimate && (
          <div className="space-y-4 text-xs">
            <div className="rounded-xl bg-base p-3 border border-border/70 space-y-2">
              <div className="flex justify-between">
                <span className="text-muted">Target Model:</span>
                <strong className="text-ink">{dryRunEstimate.model_id}</strong>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Maximum Moves per Game:</span>
                <strong className="text-ink">{dryRunEstimate.max_moves}</strong>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Max Retries per Illegal Move:</span>
                <strong className="text-ink">{dryRunEstimate.max_retries_per_move}</strong>
              </div>
              <div className="flex justify-between border-t border-border/60 pt-2 font-semibold">
                <span className="text-ink">Upper Bound API Calls:</span>
                <span className="text-accent text-sm">{dryRunEstimate.estimated_calls} calls</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Estimated Max Token Volume:</span>
                <span className="text-muted">~{dryRunEstimate.estimated_tokens_upper_bound.toLocaleString()} tokens</span>
              </div>
            </div>

            <p className="text-muted leading-relaxed">
              {dryRunEstimate.message}
            </p>

            <div className="flex justify-end gap-2 pt-2">
              <Button tone="secondary" size="sm" onClick={() => setDryRunModalOpen(false)}>
                Cancel
              </Button>
              <Button
                tone="primary"
                size="sm"
                onClick={() => {
                  setDryRunModalOpen(false)
                  handleStartGame()
                }}
              >
                Proceed to Play
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Raw Model Output / Reasoning Drawer Modal */}
      <Modal
        open={Boolean(inspectedMove)}
        onClose={() => setInspectedMove(null)}
        title={`Model Output — Ply ${inspectedMove?.ply} (${inspectedMove?.parsed_move || 'Move'})`}
        description="Inspect the exact unparsed completion produced by the model."
      >
        {inspectedMove && (
          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between text-muted">
              <span>Latency: <strong>{inspectedMove.latency_ms ? `${Math.round(inspectedMove.latency_ms)} ms` : 'N/A'}</strong></span>
              <span>Legality: <strong>{inspectedMove.is_legal ? 'Legal' : 'Illegal'}</strong></span>
            </div>
            <pre className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded-xl bg-base p-3 font-mono text-[11px] text-ink border border-border/70">
              {inspectedMove.raw_model_output}
            </pre>
            <div className="flex justify-end">
              <Button tone="secondary" size="sm" onClick={() => setInspectedMove(null)}>
                Close
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
