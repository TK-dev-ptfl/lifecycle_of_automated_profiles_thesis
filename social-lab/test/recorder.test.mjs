// The privacy-relevant part of the recorder: what is kept about a key press.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { _internal } from '../public/js/recorder.js';
const { keyCategory, hand } = _internal;

test('keys are reduced to a category; the character itself is never kept', () => {
  const cases = { a: 'l', Z: 'l', 'ž': 'l', 7: 'd', ' ': 's', ',': 'p', '@': 'p', Backspace: 'b', Delete: 'x', Enter: 'e',
    Shift: 'm', Control: 'm', ArrowLeft: 'a', Process: 'u', Dead: 'u', F5: 'o' };
  for (const [key, cat] of Object.entries(cases)) assert.equal(keyCategory({ key }), cat, key);
});

test('hand follows the physical key position (touch-typing split)', () => {
  for (const c of ['KeyQ', 'KeyT', 'KeyG', 'KeyB', 'Digit5', 'ShiftLeft']) assert.equal(hand(c), 'L', c);
  for (const c of ['KeyY', 'KeyH', 'KeyN', 'KeyP', 'Digit6', 'Digit0', 'Enter', 'Backspace']) assert.equal(hand(c), 'R', c);
  assert.equal(hand('Space'), 'S');
  assert.equal(hand('F5'), '');
});
