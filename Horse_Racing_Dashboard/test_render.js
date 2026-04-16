const fs = require('fs');
const htmlSource = fs.readFileSync('Open Dashboard.html', 'utf-8');

// Extract the needed functions
const startIdx = htmlSource.indexOf('function esc');
const endIdx = htmlSource.indexOf('function generateTopPicksHTML');
const functionsSource = htmlSource.substring(startIdx, endIdx);

// The parse function uses DASHBOARD_DATA. Not needed if we mock the data.
// Let's create an execution context
const code = `
  let currentAnalyst = 'au';
  let isMobile = false;
  ${functionsSource}
  
  const testHorse = {
    horse_number: 1,
    horse_name: "Test Horse",
    final_grade: "A",
    underhorse_triggered: true,
    underhorse_reason: 'Reason test',
    raw_text: "# Title\\nContent\\n## Sub\\nSubcontent\\n"
  };
  
  const result = renderHorseCard(testHorse, null);
  console.log("--- START RENDER ---");
  console.log(result);
  console.log("--- END RENDER ---");
  
  // simple div balancer check
  const opens = (result.match(/<div/g) || []).length;
  const closes = (result.match(/<\\/div>/g) || []).length;
  console.log("Opens:", opens, "Closes:", closes);
`;

fs.writeFileSync('run_test.js', code);
