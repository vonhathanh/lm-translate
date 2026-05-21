const BACKEND_URL = 'http://localhost:5000/api';

async function translate(text, model, language) {
  const response = await fetch(`${BACKEND_URL}/v1/translate-html`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ html: text, model, target_language: language }),
    mode: 'cors'
  });
  const result = await response.json();
  return result.translatedText;
}

const modelDropdown = document.getElementById('modelSelect');
const languageDropdown = document.getElementById('languageSelect');
const translateBtn = document.getElementById('translateBtn');

let selectedModel = modelDropdown.options[modelDropdown.selectedIndex].text;
let selectedLanguage = languageDropdown.options[languageDropdown.selectedIndex].text;

modelDropdown.addEventListener('change', (event) => {
  selectedModel = event.target.options[event.target.selectedIndex].text
});

languageDropdown.addEventListener('change', (event) => {
  selectedLanguage = event.target.options[event.target.selectedIndex].text;
});

translateBtn.addEventListener('click', async () => {
  translateBtn.textContent = 'Translating...';
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const result = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => document.body.innerHTML,
  });
  const innerHTML = result[0].result;
  const resultHtml = await translate(innerHTML, selectedModel, selectedLanguage);
  if (!resultHtml) {
    alert('Translation failed. Please try again later.');
    translateBtn.textContent = 'Translate';
    return;
  }
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    args: [resultHtml],
    func: (html) => document.body.innerHTML = html,
  });
  translateBtn.textContent = 'Translate';
});