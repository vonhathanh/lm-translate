export function load(key) {
  try {
    return JSON.parse(localStorage.getItem(key)) || {};
  } catch (e) {
    return {};
  }
}

export function save(key, s) {
  try {
    localStorage.setItem(key, JSON.stringify(s));
  } catch (e) {}
}