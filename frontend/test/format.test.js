import test from 'node:test';
import assert from 'node:assert/strict';
import { configureOrganization, localInput, localToISO, money, time } from '../src/app/format.js';

test('organization time zone, DST boundary and minor-unit currency', () => {
  configureOrganization({ locale: 'en', timezone: 'Europe/Warsaw', currency: 'EUR' });
  assert.equal(localInput('2026-01-10T12:00:00'), '2026-01-10T13:00');
  assert.equal(localToISO('2026-01-10T13:00'), '2026-01-10T12:00:00.000Z');
  assert.equal(localToISO('2026-07-10T14:00'), '2026-07-10T12:00:00.000Z');
  assert.throws(() => localToISO('2026-03-29T02:30'), /does not exist/);
  assert.throws(() => localToISO('2026-10-25T02:30'), /occurs twice/);
  assert.equal(money(12345), '123.45 EUR');
  assert.equal(money(12345, 'GBP'), '123.45 GBP');
  assert.ok(time('2026-01-10T12:00:00'));
});
