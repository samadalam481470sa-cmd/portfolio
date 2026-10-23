chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "resume-fit-fill",
    title: "Fill this page with my resume",
    contexts: ["page", "editable"],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "resume-fit-fill" && tab && tab.id) {
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["lib/matcher.js", "lib/tailor.js", "lib/autofillEngine.js", "content.js"],
    });
  }
});
