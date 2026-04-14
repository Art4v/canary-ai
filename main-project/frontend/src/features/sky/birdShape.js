/**
 * Bird shape definition for the canary SVG.
 *
 * Uses a 36×24 viewBox with bright canary-yellow colors, an ellipse-based
 * wing for natural flap animation, and a simple triangle tail/beak.
 *
 * mirrorTransform flips the bird horizontally so it faces left (flies right-to-left).
 */
const birdShape = {
  viewBox: '0 0 36 24',

  /* Simple triangle tail pointing left */
  tail: { points: '2,12 7,8 7,16', fill: '#FFD000' },

  /* Main oval body */
  body: { cx: 16, cy: 12, rx: 10, ry: 6, fill: '#FFE500' },

  /* Ellipse wing — animated with scaleY for natural flap */
  wing: { cx: 11, cy: 14, rx: 7, ry: 3, fill: '#FFD000' },

  /* Round head */
  head: { cx: 26, cy: 9, r: 5, fill: '#FFE500' },

  /* Small dark eye */
  eye: { cx: 28, cy: 8, r: 1.2, fill: '#222' },

  /* Tiny white highlight on the eye for liveliness */
  eyeHighlight: { cx: 28.5, cy: 7.5, r: 0.4, fill: '#fff' },

  /* Orange triangular beak */
  beak: { points: '31,9 35,10.5 31,12', fill: '#FF8C00' },

  /* Horizontal flip so the bird faces left (right-to-left flight) */
  mirrorTransform: 'scale(-1,1) translate(-36,0)',
}

export default birdShape
