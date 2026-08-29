const fs = require('fs');

const payloadStr = process.argv[2];
if (!payloadStr) {
    console.error("No challenge payload provided");
    process.exit(1);
}

const payload = JSON.parse(payloadStr);

// Read chunks
const c8138 = fs.readFileSync('D:/omniroute-monetizer/scratch/ds_pow_extract/8138.js', 'utf8');
let c76608 = fs.readFileSync('D:/omniroute-monetizer/scratch/ds_pow_extract/76608.js', 'utf8');

// Patch onmessage so it assigns to global
c76608 = c76608.replace('onmessage=t=>{', 'global.onmessage=t=>{');

// Mock Web Worker environment
global.self = global;
global.importScripts = function(url) {
    if (url.includes('8138')) {
        eval(c8138);
    }
};

global.postMessage = function(msg) {
    if (msg.type === 'pow-answer') {
        console.log(JSON.stringify(msg));
        process.exit(0);
    } else if (msg.type === 'pow-error') {
        console.error("Worker error:", msg.error);
        process.exit(1);
    }
};

// Execute the worker logic
try {
    eval(c76608);
    
    setTimeout(() => {
        if (typeof global.onmessage === 'function') {
            global.onmessage({
                data: {
                    type: "pow-challenge",
                    challenge: payload
                }
            });
        } else {
            console.error("onmessage not initialized");
            process.exit(1);
        }
    }, 100);
} catch (e) {
    console.error("Execution error:", e);
    process.exit(1);
}
