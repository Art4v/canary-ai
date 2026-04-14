import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import birdShape from './birdShape.js'
import './BirdLayer.css'

/**
 * Configuration for 6 birds at different depths, speeds, and flap rates.
 * Each bird flies right-to-left across the viewport with vertical bobbing.
 *
 * y      — vertical position as a percentage of the container height
 * scale  — size multiplier (smaller = farther away)
 * speed  — seconds to cross the full viewport (higher = slower)
 * flapSpeed — seconds per half-flap cycle
 * opacity — base opacity to simulate depth/atmosphere
 */
const BIRDS = [
  { id: 'b1', y: 10, scale: 0.8, speed: 18, flapSpeed: 0.3, opacity: 0.9 },
  { id: 'b2', y: 22, scale: 1.1, speed: 24, flapSpeed: 0.25, opacity: 1.0 },
  { id: 'b3', y: 38, scale: 0.6, speed: 15, flapSpeed: 0.35, opacity: 0.85 },
  { id: 'b4', y: 52, scale: 0.9, speed: 20, flapSpeed: 0.28, opacity: 0.9 },
  { id: 'b5', y: 30, scale: 0.7, speed: 28, flapSpeed: 0.32, opacity: 0.8 },
  { id: 'b6', y: 15, scale: 1.0, speed: 22, flapSpeed: 0.26, opacity: 0.95 },
]

/**
 * BirdLayer — renders 6 animated canary birds that fly right-to-left.
 *
 * Each bird's SVG is positioned absolutely within its parent container.
 * GSAP handles three concurrent animations per bird:
 *   1. Horizontal flight (right → left, infinite loop)
 *   2. Wing flap (scaleY oscillation on the wing ellipse)
 *   3. Vertical bobbing (gentle sine wave)
 */
export default function BirdLayer() {
  /* Refs keyed by bird id for the SVG container and the wing <g> element */
  const containerRefs = useRef({})
  const wingRefs = useRef({})

  useEffect(() => {
    const tweens = []

    BIRDS.forEach((bird, i) => {
      const container = containerRefs.current[bird.id]
      const wing = wingRefs.current[bird.id]
      if (!container || !wing) return

      const vw = window.innerWidth
      const birdW = 60 * bird.scale // rendered pixel width of this bird
      const startX = vw + birdW     // just off-screen right
      const endX = -birdW * 2       // safely off-screen left

      /* --- 1. Flight — right to left, infinite loop --- */
      tweens.push(
        gsap.fromTo(
          container,
          { x: startX },
          {
            x: endX,
            duration: bird.speed,
            ease: 'none',
            repeat: -1,
            delay: i * 3, // stagger each bird's entrance
            onRepeat() {
              gsap.set(container, { x: startX })
            },
          },
        ),
      )

      /* --- 2. Wing flap — rotation using svgOrigin for correct transform inside mirror <g> --- */
      /* gsap.fromTo handles both initial and target state in one tween.
         svgOrigin uses absolute SVG coordinates (18,14) — the wing's attachment
         point at the body (cx=11 + rx=7 = 18, cy=14). This works correctly
         inside the nested mirror <g transform="scale(-1,1)...">, unlike
         percentage-based transformOrigin which breaks in nested SVG transforms. */
      tweens.push(
        gsap.fromTo(wing,
          { rotation: -30 },          // wing up position
          {
            rotation: 30,             // wing down position — ±30° visible flap arc
            duration: bird.flapSpeed / 1.5, // moderate flap cadence
            svgOrigin: '18 14',       // pivot at wing-body attachment point
            ease: 'power1.inOut',     // slightly punchier than sine
            repeat: -1,
            yoyo: true,
          },
        ),
      )

      /* --- 3. Vertical bobbing — gentle sine wave while flying --- */
      tweens.push(
        gsap.to(container, {
          y: '+=12',
          duration: 1.5 + i * 0.2,
          yoyo: true,
          repeat: -1,
          ease: 'sine.inOut',
        }),
      )
    })

    /* Kill all tweens on unmount to prevent memory leaks */
    return () => tweens.forEach(t => t?.kill())
  }, [])

  return (
    <>
      {BIRDS.map(bird => (
        <svg
          key={bird.id}
          ref={el => { containerRefs.current[bird.id] = el }}
          className="bird"
          viewBox={birdShape.viewBox}
          overflow="visible"
          style={{
            top: `${bird.y}%`,
            width: `${60 * bird.scale}px`,
            '--base-opacity': bird.opacity,
          }}
        >
          {/* Mirror group — flips bird to face left for right-to-left flight */}
          <g transform={birdShape.mirrorTransform}>
            {/* Tail — simple triangle */}
            <polygon points={birdShape.tail.points} fill={birdShape.tail.fill} />

            {/* Body — main oval */}
            <ellipse
              cx={birdShape.body.cx}
              cy={birdShape.body.cy}
              rx={birdShape.body.rx}
              ry={birdShape.body.ry}
              fill={birdShape.body.fill}
            />

            {/* Wing — ellipse wrapped in <g> for scaleY flap animation */}
            <g
              ref={el => { wingRefs.current[bird.id] = el }}
              className="bird-wing"
            >
              <ellipse
                cx={birdShape.wing.cx}
                cy={birdShape.wing.cy}
                rx={birdShape.wing.rx}
                ry={birdShape.wing.ry}
                fill={birdShape.wing.fill}
              />
            </g>

            {/* Head */}
            <circle
              cx={birdShape.head.cx}
              cy={birdShape.head.cy}
              r={birdShape.head.r}
              fill={birdShape.head.fill}
            />

            {/* Eye */}
            <circle
              cx={birdShape.eye.cx}
              cy={birdShape.eye.cy}
              r={birdShape.eye.r}
              fill={birdShape.eye.fill}
            />

            {/* Eye highlight — small white dot for liveliness */}
            <circle
              cx={birdShape.eyeHighlight.cx}
              cy={birdShape.eyeHighlight.cy}
              r={birdShape.eyeHighlight.r}
              fill={birdShape.eyeHighlight.fill}
            />

            {/* Beak — orange triangle */}
            <polygon points={birdShape.beak.points} fill={birdShape.beak.fill} />
          </g>
        </svg>
      ))}
    </>
  )
}
