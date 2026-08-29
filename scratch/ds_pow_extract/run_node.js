const worker = require('./ds_worker_bundled.js');

let salt = '14391f1eeeafaed16477';
let challenge = '1251aa9c51a85fe4bedceed9ac7e1adef0900fc4e5892acb6035680c3a4fc705';

worker.setOnMessage((msg) => {
    console.log("Worker returned:", msg);
});

console.log("Sending challenge...");
worker.postMessage({
    type: "pow-challenge",
    challenge: {
        salt: salt,
        challenge: challenge,
        difficulty: 2500000
    }
});
