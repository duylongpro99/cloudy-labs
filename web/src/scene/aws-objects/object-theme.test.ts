import { describe, expect, it } from 'vitest'
import { contrastRatio, MIN_GLYPH_CONTRAST, OBJECT_THEMES, relativeLuminance } from './object-theme'

describe('contrastRatio', () => {
  it('matches the WCAG reference values', () => {
    expect(contrastRatio('#FFFFFF', '#000000')).toBeCloseTo(21, 5)
    expect(contrastRatio('#777777', '#FFFFFF')).toBeCloseTo(4.48, 2)
    expect(contrastRatio('#123456', '#123456')).toBe(1)
    expect(relativeLuminance('#FFFFFF')).toBe(1)
  })
})

describe('object palettes', () => {
  for (const [theme, palettes] of Object.entries(OBJECT_THEMES)) {
    for (const [category, p] of Object.entries(palettes)) {
      it(`${theme}/${category}: glyph on plinth reaches ${MIN_GLYPH_CONTRAST}:1`, () => {
        expect(contrastRatio(p.glyph, p.plinth)).toBeGreaterThanOrEqual(MIN_GLYPH_CONTRAST)
      })
    }
  }

  it('lifts every dark-theme plinth above its light-theme colour', () => {
    for (const [category, p] of Object.entries(OBJECT_THEMES.dark)) {
      const light = OBJECT_THEMES.light[category as keyof typeof OBJECT_THEMES.light]
      expect(relativeLuminance(p.plinth), category).toBeGreaterThan(relativeLuminance(light.plinth))
    }
  })
})
