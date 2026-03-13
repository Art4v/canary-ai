import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import birdShape from './birdShape.js'
import './BirdLayer.css'

const BIRDS = [
  { id: 'b1', y: 10, scale: 0.8, speed: 18, flapSpeed: 0.3, opacity: 0.9 },
  { id: 'b2', y: 22, scale: 1.1, speed: 24, flapSpeed: 0.25, opacity: 1.0 },
  { id: 'b3', y: 38, scale: 0.6, speed: 15, flapSpeed: 0.35, opacity: 0.85 },
  { id: 'b4', y: 52, scale: 0.9, speed: 20, flapSpeed: 0.28, opacity: 0.9 },
  { id: 'b5', y: 30, scale: 0.7, speed: 28, flapSpeed: 0.32, opacity: 0.8 },
  { id: 'b6', y: 15, scale: 1.0, speed: 22, flapSpeed: 0.26, opacity: 0.95 },
]

export default function BirdLayer() {
  const containerRefs = useRef({})
  const wingRefs = useRef({})

  useEffect(() => {
    const tweens = []

    BIRDS.forEach((bird, i) => {
      const container = containerRefs.current[bird.id]
      const wing = wingRefs.current[bird.id]
      if (!container || !wing) return

      const vw = window.innerWidth
      const birdW = 60 * bird.scale
      const startX = vw + birdW
      const endX = -birdW * 2

      // Flight — right to left
      tweens.push(
        gsap.fromTo(
          container,
          { x: startX },
          {
            x: endX,
            duration: bird.speed,
            ease: 'none',
            repeat: -1,
            delay: i * 3,
            onRepeat() {
              gsap.set(container, { x: startX })
            },
          },
        ),
      )

      // Wing flap
      tweens.push(
        gsap.to(wing, {
          rotation: 25,
          duration: bird.flapSpeed,
          yoyo: true,
          repeat: -1,
          ease: 'sine.inOut',
          transformOrigin: '25% 85%',
        }),
      )
      gsap.set(wing, { rotation: -20, transformOrigin: '25% 85%' })

      // Vertical bobbing
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
          {/* Tail */}
          <path d={birdShape.tail.d} fill={birdShape.tail.fill} />
          {/* Body */}
          <ellipse
            cx={birdShape.body.cx}
            cy={birdShape.body.cy}
            rx={birdShape.body.rx}
            ry={birdShape.body.ry}
            fill={birdShape.body.fill}
          />
          {/* Head */}
          <circle
            cx={birdShape.head.cx}
            cy={birdShape.head.cy}
            r={birdShape.head.r}
            fill={birdShape.head.fill}
          />
          {/* Wing */}
          <path
            ref={el => { wingRefs.current[bird.id] = el }}
            d={birdShape.wing.d}
            fill={birdShape.wing.fill}
          />
          {/* Beak */}
          <path d={birdShape.beak.d} fill={birdShape.beak.fill} />
          {/* Eye */}
          <circle
            cx={birdShape.eye.cx}
            cy={birdShape.eye.cy}
            r={birdShape.eye.r}
            fill={birdShape.eye.fill}
          />
        </svg>
      ))}
    </>
  )
}
