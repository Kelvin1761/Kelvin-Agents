// ==UserScript==
// @name         Bet365 NBA Wong Choi Extractor V2
// @namespace    http://tampermonkey.net/
// @version      2.0.0
// @description  One-click full extraction: auto-clicks through all Milestones tabs + reads data + POSTs to local server
// @author       Antigravity
// @match        https://www.bet365.com.au/*
// @grant        GM_xmlhttpRequest
// @connect      localhost
// ==/UserScript==

/**
 * ARCHITECTURE: Tampermonkey Full-Auto Extraction
 * 
 * Why this works when CDP clicks fail:
 * - CDP el.click() = detected by Cloudflare CDP Fingerprinting
 * - Tampermonkey click() = runs in page's trusted JS context, NOT via CDP
 * - Cloudflare cannot distinguish Tampermonkey clicks from real user clicks
 *
 * FLOW:
 * 1. User opens Bet365 NBA Index Page in Comet
 * 2. User clicks the green "EXTRACT" button (injected by this script)
 * 3. Script auto-reads Game tab (default)
 * 4. Script auto-clicks "Points" tab → waits → reads data
 * 5. Script auto-clicks "Rebounds" tab → waits → reads data
 * 6. Script auto-clicks "Assists" tab → waits → reads data  
 * 7. Script auto-clicks "Threes Made" tab → waits → reads data
 * 8. POSTs all data to localhost:8888/ingest
 * 9. Python receiver saves structured JSON
 *
 * TAB SELECTION (P40 — Milestones Source-First):
 * ✅ "Points" = Milestones (10+, 15+, 20+) — CORRECT
 * ❌ "Points O/U" = Main O/U with .5 lines — NEVER USE
 */

(function() {
    'use strict';

    // ═══════════════════════════════════════════
    //  CONFIG
    // ═══════════════════════════════════════════
    const RECEIVER_URL = 'http://localhost:8888/ingest';
    const TAB_WAIT_MS = 6000;  // Wait 6s after clicking a tab for data to render
    const RETRY_WAIT_MS = 3000;

    // P40: Correct tab names (Milestones Source-First)
    // ✅ "Points" = Milestones (10+, 15+, 20+)
    // ❌ "Points O/U" = Main O/U with .5 lines — NEVER USE
    const PROP_TABS = ["Points", "Rebounds", "Assists", "Threes Made"];

    // ═══════════════════════════════════════════
    //  HELPERS
    // ═══════════════════════════════════════════
    const sleep = ms => new Promise(r => setTimeout(r, ms));

    function isNBAPage() {
        return window.location.hash.includes('B18') || 
               document.body.innerText.includes('NBA');
    }

    function getDataSection() {
        // Strategy: Try to find the main content area first, fall back to body
        // Bet365 uses obfuscated classes, so we try multiple selectors
        let contentEl = null;
        
        // Try known Bet365 main content container selectors
        const contentSelectors = [
            '.gl-MarketGroupContainer',
            '.gl-MarketGroup',
            '.sportsbook-MainContent',
            '[class*="MarketGroup"]',
            '[class*="MainContent"]',
            '.sportsbook-ContentBlock'
        ];
        
        for (const sel of contentSelectors) {
            const el = document.querySelector(sel);
            if (el && el.innerText && el.innerText.length > 200) {
                contentEl = el;
                break;
            }
        }
        
        // Fallback: find the largest content div (heuristic)
        if (!contentEl) {
            let maxLen = 0;
            document.querySelectorAll('div').forEach(div => {
                const len = (div.innerText || '').length;
                // Must be large enough, and NOT the body itself or sidebar
                if (len > maxLen && len > 500 && len < document.body.innerText.length * 0.9) {
                    // Skip sidebar-like elements (narrow width)
                    const rect = div.getBoundingClientRect();
                    if (rect.width > 400) {
                        maxLen = len;
                        contentEl = div;
                    }
                }
            });
        }
        
        const text = contentEl ? contentEl.innerText : (document.body.innerText || '');
        const lines = text.split('\n').map(l => l.trim()).filter(l => l);
        
        // Try to find boundary markers
        let start = lines.findIndex(l => 
            l.includes('EARLY PAYOUT') || l.includes('MULTI BET OFFER') || l.includes('Player / Last 5') || l.includes('Thu') || l.includes('Fri') || l.includes('Sat')
        );
        if (start < 0) start = 0;
        
        let end = lines.findIndex(l => 
            l.includes('Receive live updates') || l.includes('Information and transmission')
        );
        if (end < 0) end = lines.length;
        
        return lines.slice(start, end);
    }

    function findTab(tabName) {
        // Search for tab elements by their text content
        // Bet365 uses various class patterns for tabs
        const selectors = [
            '.gl-MarketGroupButton',
            '[class*="NavTab"]',
            '[class*="MarketSelection"]',
            '[class*="HeaderTab"]',
            '[class*="Tab"]',
            'a', 'span', 'div'
        ];
        
        // Phase 1: Search known tab containers for EXACT match
        for (const selector of selectors) {
            const elements = document.querySelectorAll(selector);
            for (const el of elements) {
                const text = (el.innerText || '').trim();
                // Exact match only — "Points" must NOT match "Points O/U" or "Points Low"
                if (text === tabName) {
                    return el;
                }
            }
        }
        
        // Phase 2: Search leaf nodes (no children) for exact match
        const allEls = document.querySelectorAll('*');
        for (const el of allEls) {
            if (el.children.length === 0) {
                const text = (el.innerText || '').trim();
                if (text === tabName) {
                    // Extra safety: make sure this element is visible and clickable
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && rect.top < window.innerHeight) {
                        return el;
                    }
                }
            }
        }
        
        console.warn(`[WongChoi V2] findTab: Could not find "${tabName}"`);
        return null;
    }

    function checkForDecimalContamination(data) {
        // Detect .5 lines — means wrong tab was clicked
        const blob = data.join(' ');
        const matches = blob.match(/\b\d{2,}\.5\b/g);
        return matches && matches.length > 0;
    }

    // ═══════════════════════════════════════════
    //  MAIN EXTRACTION LOGIC
    // ═══════════════════════════════════════════
    async function runExtraction(statusEl) {
        const allData = {
            source: "Bet365_Tampermonkey_V2",
            timestamp: new Date().toISOString(),
            game_tags: [],
            tabs: {}
        };

        // ── Phase A: Game Lines (default tab — already selected) ──
        statusEl.innerText = '📊 Phase A: Reading Game Lines...';
        await sleep(1000);
        allData.tabs["Game Lines"] = getDataSection();
        statusEl.innerText = `✅ Game Lines: ${allData.tabs["Game Lines"].length} lines`;
        await sleep(500);

        // ── Phase B: Auto-click through Prop Tabs ──
        for (let i = 0; i < PROP_TABS.length; i++) {
            const tabName = PROP_TABS[i];
            statusEl.innerText = `🎯 Phase B [${i+1}/${PROP_TABS.length}]: Clicking "${tabName}" tab...`;

            const tabEl = findTab(tabName);
            if (!tabEl) {
                statusEl.innerText = `⚠️ Cannot find "${tabName}" tab! Skipping...`;
                allData.tabs[tabName] = [];
                await sleep(2000);
                continue;
            }

            // Click the tab (trusted page context — NOT CDP)
            tabEl.click();
            
            // Wait for SPA to render new content
            statusEl.innerText = `⏳ Waiting for "${tabName}" data to load...`;
            await sleep(TAB_WAIT_MS);

            // Read data
            const data = getDataSection();
            
            // .5 contamination check for Points tab
            if (tabName === "Points" && checkForDecimalContamination(data)) {
                statusEl.innerText = `⚠️ WRONG TAB! Found .5 lines in "${tabName}". Looking for correct tab...`;
                
                // Try to find the exact "Points" tab (not "Points O/U")
                // The issue is findTab might have matched "Points O/U" which contains "Points"
                const allTabs = document.querySelectorAll('*');
                let correctTab = null;
                for (const el of allTabs) {
                    if (el.children.length === 0) {
                        const text = (el.innerText || '').trim();
                        // Must be exactly "Points", not "Points O/U" or "Points Low"
                        if (text === "Points" && !el.parentElement?.innerText?.includes("O/U")) {
                            correctTab = el;
                            break;
                        }
                    }
                }
                
                if (correctTab && correctTab !== tabEl) {
                    correctTab.click();
                    await sleep(TAB_WAIT_MS);
                    const retryData = getDataSection();
                    if (!checkForDecimalContamination(retryData)) {
                        allData.tabs[tabName] = retryData;
                        statusEl.innerText = `✅ ${tabName}: ${retryData.length} lines (fixed!)`;
                        await sleep(500);
                        continue;
                    }
                }
                
                // Still contaminated — save anyway but warn
                statusEl.innerText = `⚠️ ${tabName}: ${data.length} lines (may contain .5 — VERIFY!)`;
                allData.tabs[tabName] = data;
                await sleep(1000);
                continue;
            }
            
            allData.tabs[tabName] = data;
            statusEl.innerText = `✅ ${tabName}: ${data.length} lines`;
            await sleep(500);
        }

        // ── Phase C: Extract game tags from Game Lines ──
        statusEl.innerText = '🏷️ Extracting game tags...';
        const gameLines = allData.tabs["Game Lines"] || [];
        // Look for team name patterns like "ATL Hawks" or "CLE Cavaliers"
        const teamPattern = /^([A-Z]{2,3})\s+\w+$/;
        const teams = [];
        for (const line of gameLines) {
            const match = line.match(teamPattern);
            if (match) {
                teams.push(match[1]);
            }
        }
        // Pair teams into game tags
        for (let i = 0; i < teams.length - 1; i += 2) {
            allData.game_tags.push(`${teams[i]}_${teams[i+1]}`);
        }

        return allData;
    }

    // ═══════════════════════════════════════════
    //  UI: Inject Extract Button
    // ═══════════════════════════════════════════
    function injectUI() {
        if (document.getElementById('wc-extract-v2')) return;

        const container = document.createElement('div');
        container.id = 'wc-extract-v2';
        container.style.cssText = `
            position: fixed; bottom: 20px; right: 20px; z-index: 999999;
            display: flex; flex-direction: column; align-items: flex-end; gap: 8px;
        `;

        const statusEl = document.createElement('div');
        statusEl.id = 'wc-status';
        statusEl.style.cssText = `
            background: #1a1a2e; color: #00ff88; padding: 8px 14px;
            border-radius: 8px; font-family: 'Courier New', monospace;
            font-size: 13px; display: none; max-width: 400px;
            border: 1px solid #00ff88; box-shadow: 0 0 15px rgba(0,255,136,0.3);
        `;

        const btn = document.createElement('button');
        btn.innerText = '🏀 EXTRACT NBA (Wong Choi V2)';
        btn.style.cssText = `
            padding: 14px 24px; background: linear-gradient(135deg, #00c853, #00e676);
            color: #000; font-weight: bold; font-size: 16px;
            border: none; border-radius: 12px; cursor: pointer;
            box-shadow: 0 4px 15px rgba(0,200,83,0.4);
            transition: all 0.3s ease;
        `;
        btn.onmouseenter = () => { btn.style.transform = 'scale(1.05)'; };
        btn.onmouseleave = () => { btn.style.transform = 'scale(1)'; };

        btn.onclick = async () => {
            btn.disabled = true;
            btn.style.background = 'linear-gradient(135deg, #ff8f00, #ffb300)';
            btn.innerText = '⏳ Extracting... (Do not touch!)';
            statusEl.style.display = 'block';

            try {
                const data = await runExtraction(statusEl);

                // Summary
                statusEl.innerText = '📡 Sending to local server...';

                // POST to local receiver
                GM_xmlhttpRequest({
                    method: "POST",
                    url: RECEIVER_URL,
                    data: JSON.stringify(data),
                    headers: { "Content-Type": "application/json" },
                    onload: function(res) {
                        if (res.status === 200) {
                            btn.innerText = '✅ SUCCESS!';
                            btn.style.background = 'linear-gradient(135deg, #00c853, #00e676)';
                            statusEl.innerText = `🏆 完成！已傳送至 Python Server\n` +
                                `Game Lines: ${(data.tabs["Game Lines"] || []).length} lines\n` +
                                `Points: ${(data.tabs["Points"] || []).length} lines\n` +
                                `Rebounds: ${(data.tabs["Rebounds"] || []).length} lines\n` +
                                `Assists: ${(data.tabs["Assists"] || []).length} lines\n` +
                                `Threes Made: ${(data.tabs["Threes Made"] || []).length} lines`;
                            statusEl.style.whiteSpace = 'pre-line';
                            
                            // Also save to console for debugging
                            console.log('[WongChoi V2] Extraction complete:', data);
                            
                            setTimeout(() => {
                                btn.disabled = false;
                                btn.innerText = '🏀 EXTRACT NBA (Wong Choi V2)';
                            }, 10000);
                        } else {
                            btn.innerText = '❌ SERVER ERROR';
                            btn.style.background = '#ff1744';
                            statusEl.innerText = `Server returned ${res.status}. Is Python receiver running?`;
                            btn.disabled = false;
                        }
                    },
                    onerror: function(err) {
                        btn.innerText = '❌ NO SERVER';
                        btn.style.background = '#ff1744';
                        statusEl.innerText = '❌ Cannot reach localhost:8888\n' +
                            '請先 run: python3 claw_bet365_receiver.py';
                        statusEl.style.whiteSpace = 'pre-line';
                        btn.disabled = false;
                        
                        // Fallback: copy to clipboard
                        const json = JSON.stringify(data, null, 2);
                        navigator.clipboard.writeText(json).then(() => {
                            statusEl.innerText += '\n📋 數據已複製到剪貼簿 (fallback)';
                        }).catch(() => {});
                    }
                });
            } catch (err) {
                btn.innerText = '❌ EXTRACTION ERROR';
                btn.style.background = '#ff1744';
                statusEl.innerText = `Error: ${err.message}`;
                btn.disabled = false;
                console.error('[WongChoi V2] Error:', err);
            }
        };

        container.appendChild(statusEl);
        container.appendChild(btn);
        document.body.appendChild(container);
    }

    // ═══════════════════════════════════════════
    //  INIT: Check for NBA page periodically
    // ═══════════════════════════════════════════
    setInterval(() => {
        if (isNBAPage()) {
            injectUI();
        } else {
            const existing = document.getElementById('wc-extract-v2');
            if (existing) existing.style.display = 'none';
        }
    }, 2000);

})();
