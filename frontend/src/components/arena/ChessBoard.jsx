/**
 * Custom SVG ChessBoard component adhering to LLM-EvalHub design tokens:
 * beige/olive tones, Source Serif typography, crisp vector pieces, and theme support.
 */

import { motion, useReducedMotion } from 'framer-motion'
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  RotateCcw,
} from 'lucide-react'
import { useCallback, useEffect, useMemo } from 'react'

// High-fidelity SVG piece vector symbols
const PIECE_PATHS = {
  P: (
    // White Pawn
    <path
      d="M22 9c-2.2 0-4 1.8-4 4 0 1.2.5 2.3 1.3 3-.9.9-1.3 2.1-1.3 3.5 0 1.2.4 2.3 1 3.2-1.9 1-3 2.9-3 5.3h16c0-2.4-1.1-4.3-3-5.3.6-.9 1-2 1-3.2 0-1.4-.4-2.6-1.3-3.5.8-.7 1.3-1.8 1.3-3 0-2.2-1.8-4-4-4z"
      className="fill-white stroke-stone-800"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  p: (
    // Black Pawn
    <path
      d="M22 9c-2.2 0-4 1.8-4 4 0 1.2.5 2.3 1.3 3-.9.9-1.3 2.1-1.3 3.5 0 1.2.4 2.3 1 3.2-1.9 1-3 2.9-3 5.3h16c0-2.4-1.1-4.3-3-5.3.6-.9 1-2 1-3.2 0-1.4-.4-2.6-1.3-3.5.8-.7 1.3-1.8 1.3-3 0-2.2-1.8-4-4-4z"
      className="fill-stone-900 stroke-stone-200"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  N: (
    // White Knight
    <path
      d="M22 10c-3 0-6 2-7 5-1 3-1 6-4 8v2c3 0 6-1 8-3v4h2v-5c1-1 3-2 4-4 1-2 1-4 0-6-.7-1-1.8-1-3-1z"
      className="fill-white stroke-stone-800"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  n: (
    // Black Knight
    <path
      d="M22 10c-3 0-6 2-7 5-1 3-1 6-4 8v2c3 0 6-1 8-3v4h2v-5c1-1 3-2 4-4 1-2 1-4 0-6-.7-1-1.8-1-3-1z"
      className="fill-stone-900 stroke-stone-200"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  ),
  B: (
    // White Bishop
    <g
      className="fill-white stroke-stone-800"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M19 12c-2 2-3 5-3 8h12c0-3-1-6-3-8-1-1-2-1-3-1s-2 0-3 1z" />
      <circle cx="22" cy="10" r="2.5" />
      <path d="M16 28h12v3H16z" />
    </g>
  ),
  b: (
    // Black Bishop
    <g
      className="fill-stone-900 stroke-stone-200"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M19 12c-2 2-3 5-3 8h12c0-3-1-6-3-8-1-1-2-1-3-1s-2 0-3 1z" />
      <circle cx="22" cy="10" r="2.5" />
      <path d="M16 28h12v3H16z" />
    </g>
  ),
  R: (
    // White Rook
    <g
      className="fill-white stroke-stone-800"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M14 11h3v4h2v-4h6v4h2v-4h3v6h-2l-1 9h-10l-1-9h-2z" />
      <path d="M12 28h20v4H12z" />
    </g>
  ),
  r: (
    // Black Rook
    <g
      className="fill-stone-900 stroke-stone-200"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M14 11h3v4h2v-4h6v4h2v-4h3v6h-2l-1 9h-10l-1-9h-2z" />
      <path d="M12 28h20v4H12z" />
    </g>
  ),
  Q: (
    // White Queen
    <g
      className="fill-white stroke-stone-800"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M13 14l3 9h12l3-9-4 4-5-8-5 8z" />
      <circle cx="13" cy="13" r="1.5" />
      <circle cx="19" cy="9" r="1.5" />
      <circle cx="25" cy="9" r="1.5" />
      <circle cx="31" cy="13" r="1.5" />
      <path d="M14 26h16v4H14z" />
    </g>
  ),
  q: (
    // Black Queen
    <g
      className="fill-stone-900 stroke-stone-200"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M13 14l3 9h12l3-9-4 4-5-8-5 8z" />
      <circle cx="13" cy="13" r="1.5" />
      <circle cx="19" cy="9" r="1.5" />
      <circle cx="25" cy="9" r="1.5" />
      <circle cx="31" cy="13" r="1.5" />
      <path d="M14 26h16v4H14z" />
    </g>
  ),
  K: (
    // White King
    <g
      className="fill-white stroke-stone-800"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M22 6v6m-3-3h6" />
      <path d="M16 16c2-2 4-3 6-3s4 1 6 3c1 2 1 5-1 7l-1 4h-8l-1-4c-2-2-2-5-1-7z" />
      <path d="M14 28h16v4H14z" />
    </g>
  ),
  k: (
    // Black King
    <g
      className="fill-stone-900 stroke-stone-200"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M22 6v6m-3-3h6" />
      <path d="M16 16c2-2 4-3 6-3s4 1 6 3c1 2 1 5-1 7l-1 4h-8l-1-4c-2-2-2-5-1-7z" />
      <path d="M14 28h16v4H14z" />
    </g>
  ),
}

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
const RANKS = ['8', '7', '6', '5', '4', '3', '2', '1']

export function parseFenBoard(fen) {
  if (!fen) return Array(8).fill(null).map(() => Array(8).fill(null))
  const boardPart = fen.trim().split(' ')[0]
  const rows = boardPart.split('/')
  const grid = []

  for (let r = 0; r < 8; r++) {
    const row = []
    const rowStr = rows[r] || ''
    for (let c = 0; c < rowStr.length; c++) {
      const char = rowStr[c]
      if (char >= '1' && char <= '8') {
        const emptyCount = parseInt(char, 10)
        for (let e = 0; e < emptyCount; e++) row.push(null)
      } else {
        row.push(char)
      }
    }
    grid.push(row)
  }
  return grid
}

export default function ChessBoard({
  fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
  highlightSquares = [],
  checkSquare = null,
  currentPly = 0,
  maxPly = 0,
  onPlyChange = null,
  className = '',
}) {
  const shouldReduceMotion = useReducedMotion()
  const boardGrid = useMemo(() => parseFenBoard(fen), [fen])

  const handlePrev = useCallback(() => {
    if (onPlyChange && currentPly > 0) onPlyChange(currentPly - 1)
  }, [onPlyChange, currentPly])

  const handleNext = useCallback(() => {
    if (onPlyChange && currentPly < maxPly) onPlyChange(currentPly + 1)
  }, [onPlyChange, currentPly, maxPly])

  const handleStart = useCallback(() => {
    if (onPlyChange) onPlyChange(0)
  }, [onPlyChange])

  const handleEnd = useCallback(() => {
    if (onPlyChange) onPlyChange(maxPly)
  }, [onPlyChange, maxPly])

  // Keyboard navigation for scrubber
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
      if (e.key === 'ArrowLeft') {
        handlePrev()
      } else if (e.key === 'ArrowRight') {
        handleNext()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handlePrev, handleNext])

  return (
    <div className={`flex flex-col items-center gap-3 ${className}`}>
      {/* 8x8 Board Container */}
      <div className="relative rounded-2xl border border-border/80 bg-surface p-2 shadow-card">
        <svg
          viewBox="0 0 352 352"
          className="h-80 w-80 select-none sm:h-96 sm:w-96"
          aria-label="Interactive Chess Board"
        >
          {/* Coordinates margins & square dimensions */}
          <g transform="translate(16, 16)">
            {/* Draw 64 squares */}
            {RANKS.map((rank, rIdx) =>
              FILES.map((file, fIdx) => {
                const squareName = `${file}${rank}`
                const isLight = (rIdx + fIdx) % 2 === 0
                const isHighlighted = highlightSquares.includes(squareName)
                const isCheck = checkSquare === squareName

                let fill = isLight ? '#f9f7f2' : '#dcd6c6'
                if (isHighlighted) fill = '#c8d4a6' // subtle olive highlight
                if (isCheck) fill = '#fecaca' // red check alert

                return (
                  <rect
                    key={squareName}
                    x={fIdx * 40}
                    y={rIdx * 40}
                    width={40}
                    height={40}
                    fill={fill}
                    className="transition-colors duration-150"
                  />
                )
              }),
            )}

            {/* Rank indicators (1-8 on left) */}
            {RANKS.map((rank, rIdx) => (
              <text
                key={`rank-${rank}`}
                x={-6}
                y={rIdx * 40 + 24}
                className="fill-muted font-sans text-[11px] font-medium"
                textAnchor="middle"
              >
                {rank}
              </text>
            ))}

            {/* File indicators (a-h along bottom) */}
            {FILES.map((file, fIdx) => (
              <text
                key={`file-${file}`}
                x={fIdx * 40 + 20}
                y={334}
                className="fill-muted font-sans text-[11px] font-medium"
                textAnchor="middle"
              >
                {file}
              </text>
            ))}

            {/* Pieces */}
            {boardGrid.map((row, rIdx) =>
              row.map((piece, fIdx) => {
                if (!piece) return null
                const squareName = `${FILES[fIdx]}${RANKS[rIdx]}`
                const pieceSvg = PIECE_PATHS[piece]
                if (!pieceSvg) return null

                return (
                  <g
                    key={`piece-${squareName}-${piece}`}
                    transform={`translate(${fIdx * 40 - 2}, ${rIdx * 40 - 2}) scale(0.98)`}
                  >
                    {pieceSvg}
                  </g>
                )
              }),
            )}
          </g>
        </svg>
      </div>

      {/* Scrubber / Ply stepper controls */}
      {onPlyChange && maxPly > 0 && (
        <div className="flex items-center gap-1.5 rounded-xl border border-border/80 bg-surface px-3 py-1.5 shadow-sm">
          <button
            type="button"
            onClick={handleStart}
            disabled={currentPly === 0}
            className="rounded-lg p-1.5 text-muted hover:bg-base hover:text-ink disabled:opacity-30"
            title="Start of game"
            aria-label="Start of game"
          >
            <ChevronsLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={handlePrev}
            disabled={currentPly === 0}
            className="rounded-lg p-1.5 text-muted hover:bg-base hover:text-ink disabled:opacity-30"
            title="Previous move (Left arrow)"
            aria-label="Previous move"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          <span className="min-w-24 text-center font-serif text-xs font-semibold text-ink">
            Ply {currentPly} / {maxPly}
          </span>

          <button
            type="button"
            onClick={handleNext}
            disabled={currentPly === maxPly}
            className="rounded-lg p-1.5 text-muted hover:bg-base hover:text-ink disabled:opacity-30"
            title="Next move (Right arrow)"
            aria-label="Next move"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={handleEnd}
            disabled={currentPly === maxPly}
            className="rounded-lg p-1.5 text-muted hover:bg-base hover:text-ink disabled:opacity-30"
            title="Current live position"
            aria-label="Current live position"
          >
            <ChevronsRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  )
}
