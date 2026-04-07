// ==UserScript==
// @name         Bet365 NBA Extractor (Wong Choi)
// @namespace    http://tampermonkey.net/
// @version      0.1
// @description  Extracts NBA odds directly from the browser DOM
// @author       Antigravity
// @match        https://www.bet365.com.au/*
// @grant        GM_xmlhttpRequest
// ==/UserScript==

(function() {
    'use strict';

    setInterval(() => {
        // Only show button if we are in Basketball section
        if (!window.location.hash.includes('B18') && !window.location.hash.includes('B18')) {
            let existingBtn = document.getElementById('wc-extractor-btn');
            if (existingBtn) existingBtn.style.display = 'none';
            return;
        }
        
        let extractBtn = document.getElementById('wc-extractor-btn');
        // If button doesn't exist yet, create it
        if (!extractBtn) {
            extractBtn = document.createElement('button');
            extractBtn.id = 'wc-extractor-btn';
            extractBtn.innerText = '✅ EXTRACT NBA ODDS';
            extractBtn.style.position = 'fixed';
            extractBtn.style.bottom = '20px';
            extractBtn.style.right = '20px';
            extractBtn.style.zIndex = '999999';
            extractBtn.style.padding = '15px 25px';
            extractBtn.style.backgroundColor = '#00ff00';
            extractBtn.style.color = '#000';
            extractBtn.style.fontWeight = 'bold';
            extractBtn.style.fontSize = '18px';
            extractBtn.style.border = '2px solid #000';
            extractBtn.style.cursor = 'pointer';
            
            document.body.appendChild(extractBtn);

            extractBtn.onclick = async () => {
                extractBtn.innerText = '⏳ Extracting... (Do not click)';
                extractBtn.style.backgroundColor = '#ffff00';
                
                let all_data = {
                    "source": "Bet365_Tampermonkey",
                    "games_raw": [],
                    "props_raw": {}
                };

                const sleep = ms => new Promise(r => setTimeout(r, ms));
                const getLines = () => {
                    let c = document.querySelector('.gl-MarketGroupContainer') || document.querySelector('.gl-MarketGroup');
                    return c ? c.innerText.split('\\n') : [];
                };

                // 1. Ensure we are in NBA games
                let titleEls = Array.from(document.querySelectorAll('.sph-EventHeader_Label, .sm-StandardMarker_Text'));
                let inNba = titleEls.some(e => e.innerText && e.innerText.includes('NBA'));
                
                if (!inNba) {
                    let nbaBtn = [...document.querySelectorAll('.sm-StandardMarker_Text')].find(e => e.innerText === 'NBA');
                    if (nbaBtn) {
                        nbaBtn.click();
                        await sleep(4000);
                    }
                }

                // Game Lines
                all_data.games_raw = getLines();

                // Props helper
                async function getProp(name) {
                    let tab = [...document.querySelectorAll('.hsn-NavTab_Label')].find(e => e.innerText === name);
                    if (tab) {
                        tab.click();
                        await sleep(3500);
                        return getLines();
                    }
                    return [];
                }

                all_data.props_raw["Points"] = await getProp("Points O/U");
                all_data.props_raw["Assists"] = await getProp("Assists");
                all_data.props_raw["Rebounds"] = await getProp("Rebounds");
                all_data.props_raw["Threes"] = await getProp("Threes Made");

                console.log("[WongChoi] Data prepared: ", all_data);

                // Post to Local Server
                GM_xmlhttpRequest({
                    method: "POST",
                    url: "http://localhost:8888/ingest",
                    data: JSON.stringify(all_data),
                    headers: { "Content-Type": "application/json" },
                    onload: function(res) {
                        if (res.status === 200) {
                            extractBtn.innerText = '✅ SUCCESS! (Self-Destruct in 3s)';
                            extractBtn.style.backgroundColor = '#00ff00';
                            setTimeout(() => extractBtn.remove(), 3000);
                        } else {
                            extractBtn.innerText = '❌ SERVER ERROR';
                            extractBtn.style.backgroundColor = '#ff0000';
                        }
                    },
                    onerror: function() {
                        extractBtn.innerText = '❌ LOCAL SERVER OFFLINE (Is Python running?)';
                        extractBtn.style.backgroundColor = '#ff0000';
                    }
                });
            };
        } else {
            extractBtn.style.display = 'block';
        }
    }, 2000);
})();
