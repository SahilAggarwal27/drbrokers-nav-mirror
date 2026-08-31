/*
 * navfetch.js — shared NAV fetcher for all DR Brokers dashboards.
 *
 * WHY: every tool reimplemented mfapi.in fetching, so every mfapi outage blanked
 * every tool and every fix had to be repeated 9 times. This is ONE module:
 *   mirror-first (your self-hosted AMFI cache) → mfapi.in fallback → last-good.
 * mfapi outages become invisible because the mirror is served from your own
 * GitHub Pages / Cloudflare and doesn't depend on mfapi being up.
 *
 * RESPONSE SHAPE (identical to mfapi, so tools need no parsing changes):
 *   { meta:{ scheme_code, scheme_name }, data:[ { date:"DD-MM-YYYY", nav:"123.45" }, ... ] }
 *   data is newest-first.
 *
 * INTEGRATION (per tool): replace the tool's own fetchNavHistoryOnce with a call
 * to NavFetch.fetchOne(code), or use NavFetch.prime(codes, onProgress) to bulk
 * pre-fetch. The rest of each tool (snapshot building, matching) is unchanged.
 */
(function (global) {
  "use strict";

  const DEFAULTS = {
    // Your mirror base. Serves /mf/<code>.json in mfapi shape.
    // GitHub Pages: https://sahilaggarwal27.github.io/drbrokers-nav-mirror/mf/
    // or a Cloudflare Pages custom domain, e.g. https://nav.drbrokers.in/mf/
    mirrorBase: "https://sahilaggarwal27.github.io/drbrokers-nav-mirror/mf/",
    mfapiBase:  "https://api.mfapi.in/mf/",
    batchSize:  25,
    waveDelayMs: 120,
    perReqTimeoutMs: 10000,
    retryPasses: 4,
    backoffMs: [0, 800, 2000, 4500],
    lastGoodKey: "drb_navfetch_lastgood_v1",
    completenessGood: 0.80,
    useMfapiFallback: true,   // set false once the mirror is fully seeded to go 100% independent
  };

  const RETRYABLE_STATUS = new Set([429, 500, 502, 503, 504]);

  function timeoutFetch(url, ms) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), ms);
    return fetch(url, { signal: ctrl.signal })
      .finally(() => clearTimeout(t));
  }

  // Returns { data, name } on success, { retry:true } if transient, { data:[], name:"" } if definitively empty.
  async function tryUrl(url, timeoutMs) {
    try {
      const r = await timeoutFetch(url, timeoutMs);
      if (RETRYABLE_STATUS.has(r.status)) return { retry: true };
      if (!r.ok) return { data: [], name: "" };          // 404 → definitively no data
      const j = await r.json();
      const data = (j && j.data && j.data.length) ? j.data : [];
      const name = (j && j.meta && j.meta.scheme_name) ? j.meta.scheme_name : "";
      return { data, name };
    } catch (e) {
      return { retry: true };                             // abort / network / timeout
    }
  }

  const NavFetch = {
    cfg: Object.assign({}, DEFAULTS),

    configure(opts) { Object.assign(this.cfg, opts || {}); return this; },

    /*
     * Fetch one scheme's history. Mirror first; on retryable/empty, fall back to
     * mfapi (if enabled). Single attempt — retry orchestration lives in prime().
     */
    async fetchOne(code) {
      const c = this.cfg;
      let res = await tryUrl(c.mirrorBase + code + ".json", c.perReqTimeoutMs);
      if (res.data && res.data.length) return res;
      // mirror missed this code (not yet seeded) or transient — try mfapi
      if (c.useMfapiFallback) {
        const m = await tryUrl(c.mfapiBase + code, c.perReqTimeoutMs);
        if (m.data && m.data.length) return m;
        if (m.retry) return { retry: true };
      }
      return res.retry ? { retry: true } : { data: [], name: "" };
    },

    /*
     * Bulk pre-fetch a list of codes with waves + multi-pass retry + backoff.
     * Returns Map<code, {data,name}> (empty data == no NAV available).
     * onProgress({done,total,withData}) fires after each wave.
     */
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
      // exhausted retries → mark remaining empty
      pending.forEach(code => { if (!out.has(code)) out.set(code, { data: [], name: "" }); });
      return out;
    },

    completeness(map, codes) {
      if (!codes.length) return 0;
      let withData = 0;
      codes.forEach(c => { const v = map.get(String(c)) || map.get(c); if (v && v.data.length) withData++; });
      return withData / codes.length;
    },

    // ---- last-good persistence (survives mfapi outages across reloads) ----
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
