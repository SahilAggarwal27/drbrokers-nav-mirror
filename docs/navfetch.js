/*
 * navfetch.js — shared NAV fetcher for all DR Brokers dashboards.
 * Served from GitHub Pages at /drbrokers-nav-mirror/navfetch.js
 *
 * mirror-first (self-hosted AMFI cache) -> mfapi.in fallback -> last-good.
 * Response shape matches mfapi exactly:
 *   { meta:{ scheme_code, scheme_name }, data:[ { date:"DD-MM-YYYY", nav:"123.45" }, ... ] }  // newest-first
 */
(function (global) {
  "use strict";

  const DEFAULTS = {
    mirrorBase: "https://sahilaggarwal27.github.io/drbrokers-nav-mirror/mf/",
    mfapiBase:  "https://api.mfapi.in/mf/",
    batchSize:  25,
    waveDelayMs: 120,
    perReqTimeoutMs: 10000,
    retryPasses: 4,
    backoffMs: [0, 800, 2000, 4500],
    lastGoodKey: "drb_navfetch_lastgood_v1",
    completenessGood: 0.80,
    useMfapiFallback: true,
  };

  const RETRYABLE_STATUS = new Set([429, 500, 502, 503, 504]);

  function timeoutFetch(url, ms) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), ms);
    return fetch(url, { signal: ctrl.signal }).finally(() => clearTimeout(t));
  }

  async function tryUrl(url, timeoutMs) {
    try {
      const r = await timeoutFetch(url, timeoutMs);
      if (RETRYABLE_STATUS.has(r.status)) return { retry: true };
      if (!r.ok) return { data: [], name: "" };
      const j = await r.json();
      const data = (j && j.data && j.data.length) ? j.data : [];
      const name = (j && j.meta && j.meta.scheme_name) ? j.meta.scheme_name : "";
      return { data, name };
    } catch (e) {
      return { retry: true };
    }
  }

  const NavFetch = {
    cfg: Object.assign({}, DEFAULTS),
    configure(opts) { Object.assign(this.cfg, opts || {}); return this; },

    async fetchOne(code) {
      const c = this.cfg;
      let res = await tryUrl(c.mirrorBase + code + ".json", c.perReqTimeoutMs);
      if (res.data && res.data.length) return res;
      if (c.useMfapiFallback) {
        const m = await tryUrl(c.mfapiBase + code, c.perReqTimeoutMs);
        if (m.data && m.data.length) return m;
        if (m.retry) return { retry: true };
      }
      return res.retry ? { retry: true } : { data: [], name: "" };
    },

    async prime(codes, onProgress) {
      const c = this.cfg;
      const out = new Map();
      let pending = codes.slice();
      for (let pass = 0; pass < c.retryPasses && pending.length; pass++) {
        if (pass > 0) await sleep(c.backoffMs[Math.min(pass, c.backoffMs.length - 1)]);
        const next = [];
        for (let i = 0; i < pending.length; i += c.batchSize) {
          const wave = pending.slice(i, i + c.batchSize);
          const results = await Promise.all(wave.map(code => this.fetchOne(code)));
          wave.forEach((code, k) => {
            const r = results[k];
            if (r && r.retry) { next.push(code); }
            else { out.set(code, { data: r.data || [], name: r.name || "" }); }
          });
          if (onProgress) {
            const withData = [...out.values()].filter(v => v.data.length).length;
            onProgress({ done: out.size, total: codes.length, withData, pass });
          }
          if (i + c.batchSize < pending.length) await sleep(c.waveDelayMs);
        }
        pending = next;
      }
      pending.forEach(code => { if (!out.has(code)) out.set(code, { data: [], name: "" }); });
      return out;
    },

    completeness(map, codes) {
      if (!codes.length) return 0;
      let withData = 0;
      codes.forEach(c => { const v = map.get(String(c)) || map.get(c); if (v && v.data.length) withData++; });
      return withData / codes.length;
    },

    saveLastGood(payload, comp) {
      try {
        const prev = this.loadLastGood();
        if (!prev || comp >= (prev._completeness || 0)) {
          localStorage.setItem(this.cfg.lastGoodKey,
            JSON.stringify(Object.assign({}, payload, { _completeness: comp, _ts: Date.now() })));
          return true;
        }
      } catch (e) {}
      return false;
    },
    loadLastGood() {
      try { return JSON.parse(localStorage.getItem(this.cfg.lastGoodKey) || "null"); }
      catch (e) { return null; }
    },
    clearLastGood() { try { localStorage.removeItem(this.cfg.lastGoodKey); } catch (e) {} },
  };

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
  global.NavFetch = NavFetch;
})(typeof window !== "undefined" ? window : this);
