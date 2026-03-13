import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import cloudShapes from './cloudShapes.js'
import './CloudLayer.css'

const CLOUDS = [
  { id: 'c1', shapeIndex: 0, y: 8, scale: 1.3, speed: 70, opacity: 0.9, zIndex: 1 },
  { id: 'c2', shapeIndex: 1, y: 20, scale: 1.0, speed: 55, opacity: 1.0, zIndex: 2 },
  { id: 'c3', shapeIndex: 2, y: 35, scale: 0.8, speed: 45, opacity: 0.85, zIndex: 1 },
  { id: 'c4', shapeIndex: 0, y: 50, scale: 1.1, speed: 65, opacity: 0.8, zIndex: 1 },
  { id: 'c5', shapeIndex: 1, y: 65, scale: 0.9, speed: 50, opacity: 0.9, zIndex: 2 },
  { id: 'c6', shapeIndex: 2, y: 15, scale: 0.7, speed: 40, opacity: 0.8, zIndex: 1 },
  { id: 'c7', shapeIndex: 0, y: 75, scale: 1.0, speed: 60, opacity: 0.85, zIndex: 1 },
]

export default function CloudLayer() {
  const refs = useRef({})

  useEffect(() => {
    const tweens = CLOUDS.map((cloud, i) => {
      const el = refs.current[cloud.id]
      if (!el) return null

      const vw = window.innerWidth
      const cloudW = 300 * cloud.scale
      const startX = vw + cloudW * 0.5
      const endX = -cloudW * 1.5

      return gsap.fromTo(
        el,
        { x: startX },
        {
          x: endX,
          duration: cloud.speed,
          ease: 'power1.inOut',
          repeat: -1,
          delay: i * 8,
          onRepeat() {
            gsap.set(el, { x: startX })
          },
        },
      )
    })

    return () => tweens.forEach(t => t?.kill())
  }, [])

  return (
    <>
      {CLOUDS.map(cloud => {
        const shape = cloudShapes[cloud.shapeIndex]
        return (
          <svg
            key={cloud.id}
            ref={el => { refs.current[cloud.id] = el }}
            className="cloud"
            viewBox={shape.viewBox}
            overflow="visible"
            style={{
              top: `${cloud.y}%`,
              width: `${300 * cloud.scale}px`,
              '--base-opacity': cloud.opacity,
              zIndex: cloud.zIndex,
            }}
          >
            {shape.ellipses.map((e, i) => (
              <ellipse
                key={i}
                cx={e.cx}
                cy={e.cy}
                rx={e.rx}
                ry={e.ry}
                fill="var(--color-cloud)"
              />
            ))}
          </svg>
        )
      })}
    </>
  )
}
