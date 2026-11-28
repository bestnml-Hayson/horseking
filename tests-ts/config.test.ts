import test from 'node:test'
import assert from 'node:assert/strict'

import {
  ACTIVE_PROFILE_NAME,
  MODEL_WEIGHT,
  MARKET_WEIGHT,
  calibratePModel,
  fusionAlpha,
  getWeightsByVenue,
  marketProbabilities,
} from '../lib/race-utils'
import profiles from '../config/model_profiles.json'

const config = profiles as unknown as {
  default_profile: string
  profiles: Record<string, { extends?: string; weights?: Record<string, Record<string, number>> }>
}

function approx(actual: number, expected: number, eps = 1e-9) {
  assert.ok(Math.abs(actual - expected) < eps, `${actual} != ${expected}`)
}

function resolveWeights(name: string): Record<string, Record<string, number>> | undefined {
  let current: string | undefined = name
  while (current) {
    const spec: { extends?: string; weights?: Record<string, Record<string, number>> } | undefined =
      config.profiles[current]
    assert.ok(spec, `unknown profile ${current}`)
    if (spec.weights) return spec.weights
    current = spec.extends
  }
  return undefined
}

test('default profile is current_v586', () => {
  assert.equal(config.default_profile, 'current_v586')
  assert.equal(ACTIVE_PROFILE_NAME, config.default_profile)
  approx(MODEL_WEIGHT, 0.2)
  approx(MARKET_WEIGHT, 0.8)
})

test('weights come from the shared config, not a second copy', () => {
  const weights = resolveWeights(config.default_profile)
  assert.ok(weights)
  for (const venue of ['HV', 'ST'] as const) {
    const fromConfig = weights[venue]
    const fromEngine = getWeightsByVenue(venue)
    for (const key of Object.keys(fromConfig)) {
      approx(fromEngine[key as keyof typeof fromEngine], fromConfig[key])
    }
    const total = Object.values(fromEngine).reduce((a, b) => a + b, 0)
    approx(total, 1, 1e-6)
  }
})

test('every profile table sums to 1 with the nine factor keys', () => {
  for (const name of Object.keys(config.profiles)) {
    const weights = resolveWeights(name)
    for (const venue of ['HV', 'ST'] as const) {
      assert.ok(weights?.[venue], `${name}.${venue}`)
      assert.equal(Object.keys(weights[venue]).length, 9, `${name}.${venue}`)
      approx(Object.values(weights[venue]).reduce((a, b) => a + b, 0), 1, 1e-4)
    }
  }
})

test('market probabilities strip the takeout', () => {
  const probs = marketProbabilities([2, 4])
  approx(probs[0], 2 / 3)
  approx(probs[1], 1 / 3)
  approx(probs[0] + probs[1], 1)
})

test('missing odds stay zero instead of inventing a price', () => {
  const probs = marketProbabilities([null, 2])
  approx(probs[0], 0)
  approx(probs[1], 1)
})

test('calibration is the identity in the default profile', () => {
  const input = [0.1, 0.2, 0.7]
  const out = calibratePModel(input)
  out.forEach((p, i) => approx(p, input[i]))
})

test('fusion alpha lifts only at the configured extreme band', () => {
  approx(fusionAlpha(3), 0.2)
  approx(fusionAlpha(1.5), 0.35)
  approx(fusionAlpha(30), 0.35)
  approx(fusionAlpha(null), 0.2)
})