import json, sys
from pathlib import Path
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from cdp import Page

with Page("chat.cerebras.ai", port=9222) as p:
    # Look for model selector options in DOM
    try:
        opts = p.evaluate("""(()=>{
            const out=[];
            document.querySelectorAll('select option, [role="option"], [data-model], button').forEach(el=>{
                const t=(el.textContent||'').trim();
                if(t && t.length<40 && /[a-z0-9]/i.test(t)) out.push(t);
            });
            return JSON.stringify([...new Set(out)].slice(0,60));
        })()""")
        print("DOM candidates:", opts)
    except Exception as e:
        print("dom err:", e)
    # Search page HTML for model id patterns
    try:
        models = p.evaluate("""(()=>{
            const html=document.documentElement.innerHTML;
            const re=/["']([a-z0-9][a-z0-9.\\-_]{2,40})["']\\s*[:,]\\s*["']?(?:model|id)/gi;
            const set=new Set();
            const known=['llama','qwen','gemma','deepseek','mistral'];
            const re2=/\\b((?:llama|qwen|gemma|deepseek|mistral)[a-z0-9.\\-_]{0,30})\\b/gi;
            let m; while((m=re2.exec(html))){set.add(m[1]);}
            return JSON.stringify([...set].slice(0,40));
        })()""")
        print("model-ish strings in HTML:", models)
    except Exception as e:
        print("html err:", e)
    # Next.js data
    try:
        nd = p.evaluate("""(()=>{
            const s=document.getElementById('__NEXT_DATA__');
            return s? s.textContent.slice(0,200):'no __NEXT_DATA__';
        })()""")
        print("__NEXT_DATA__:", nd)
    except Exception as e:
        print("nd err:", e)
