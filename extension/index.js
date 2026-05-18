const BACKEND_URL = 'http://localhost:5000/api';

async function translate(text, model, language) {
  const response = await fetch(`${BACKEND_URL}/v1/translate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ text, model, language }),
    mode: 'cors'
  });
  const result = await response.json();
  console.log('result:', result.translatedText);
  return result.translatedText;
}

const modelDropdown = document.getElementById('modelSelect');
const languageDropdown = document.getElementById('languageSelect');
const translateBtn = document.getElementById('translateBtn');

let selectedModel = modelDropdown.value;
let selectedLanguage = languageDropdown.value;

modelDropdown.addEventListener('change', (event) => {
  selectedModel = event.target.options[event.target.selectedIndex].text
  console.log("Selected model:", selectedModel);
});

languageDropdown.addEventListener('change', (event) => {
  selectedLanguage = event.target.options[event.target.selectedIndex].text;
  console.log("Selected language:", selectedLanguage);
});

translateBtn.addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const result = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => document.body.innerHTML,
  });
  const innerHTML = result[0].result;
  console.log("Translating innerHTML:", innerHTML, "using model:", selectedModel, "and language:", selectedLanguage);
  const resultHtml = await translate(innerHTML, selectedModel, selectedLanguage);
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => document.body.innerHTML = 'hello world',
  });
});