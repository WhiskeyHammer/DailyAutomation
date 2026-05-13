const fs = require('fs');
const path = require('path');

// Get the log file from command line or find the most recent one
let logFile = process.argv[2];

if (!logFile) {
  // Find the most recent interaction-log file
  const files = fs.readdirSync(__dirname)
    .filter(f => f.startsWith('interaction-log-') && f.endsWith('.json'))
    .sort()
    .reverse();

  if (files.length === 0) {
    console.error('❌ No interaction log files found. Run recorder.js first.');
    process.exit(1);
  }

  logFile = path.join(__dirname, files[0]);
  console.log(`📖 Analyzing: ${path.basename(logFile)}\n`);
} else {
  logFile = path.resolve(logFile);
}

const data = JSON.parse(fs.readFileSync(logFile, 'utf8'));

console.log('═'.repeat(60));
console.log('INTERACTION SUMMARY');
console.log('═'.repeat(60));
console.log(`⏱️  Duration: ${(data.recordingDuration / 1000).toFixed(1)}s`);
console.log(`📊 Total Interactions: ${data.totalInteractions}`);
console.log(`⏰ Started: ${data.startTime}`);
console.log(`⏰ Ended: ${data.endTime}`);
console.log('');

// Count by type
const byType = {};
data.interactions.forEach(int => {
  byType[int.type] = (byType[int.type] || 0) + 1;
});

console.log('Interactions by Type:');
Object.entries(byType)
  .sort((a, b) => b[1] - a[1])
  .forEach(([type, count]) => {
    console.log(`  ${type.padEnd(15)} : ${count}`);
  });

console.log('\n' + '═'.repeat(60));
console.log('INTERACTION TIMELINE');
console.log('═'.repeat(60) + '\n');

data.interactions.forEach((int, idx) => {
  const time = new Date(int.timestamp).toLocaleTimeString();

  switch (int.type) {
    case 'click':
      console.log(`${(idx + 1).toString().padStart(3)}. [${time}] 🖱️  CLICK on ${int.element.tag}${int.element.id ? `#${int.element.id}` : ''}`);
      if (int.element.text) console.log(`      Text: "${int.element.text}"`);
      if (int.x !== undefined) console.log(`      Position: (${int.x}, ${int.y})`);
      break;

    case 'input':
      console.log(`${(idx + 1).toString().padStart(3)}. [${time}] ⌨️  INPUT on ${int.element.tag}${int.element.name ? `[name="${int.element.name}"]` : ''}`);
      if (int.value) console.log(`      Value: "${int.value}"`);
      break;

    case 'submit':
      console.log(`${(idx + 1).toString().padStart(3)}. [${time}] ✅ SUBMIT form${int.element.id ? `#${int.element.id}` : ''}`);
      break;

    case 'navigation':
      console.log(`${(idx + 1).toString().padStart(3)}. [${time}] 🌐 NAVIGATE to ${int.url}`);
      break;
  }
});

console.log('\n' + '═'.repeat(60));
console.log('To get more details, open the JSON file:');
console.log(logFile);
