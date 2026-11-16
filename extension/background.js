// Listen for oauth_token cookie on accounts.google.com
chrome.cookies.onChanged.addListener((changeInfo) => {
  if (changeInfo.cookie && changeInfo.cookie.name === "oauth_token") {
    if (!changeInfo.removed) {
      const tokenVal = changeInfo.cookie.value;
      chrome.storage.local.set({ oauth_token: tokenVal, timestamp: Date.now() });
    }
  }
});
