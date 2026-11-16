const WEB_APP_URL = "https://pp-mod-auto-quest.onrender.com";

document.addEventListener("DOMContentLoaded", () => {
  const btnOpenGoogle = document.getElementById("btnOpenGoogle");
  const statusText = document.getElementById("statusText");
  const tokenSection = document.getElementById("tokenSection");
  const tokenVal = document.getElementById("tokenVal");
  const btnCopy = document.getElementById("btnCopy");
  const btnOpenWeb = document.getElementById("btnOpenWeb");

  let currentToken = "";

  // 1. Check existing cookie directly
  chrome.cookies.get({ url: "https://accounts.google.com", name: "oauth_token" }, (cookie) => {
    if (cookie && cookie.value) {
      showToken(cookie.value);
    } else {
      // Check local storage fallback
      chrome.storage.local.get(["oauth_token"], (res) => {
        if (res.oauth_token) {
          showToken(res.oauth_token);
        } else {
          statusText.innerText = "টোকেন এখনো পাওয়া যায়নি। ওপরের বাটনে চাপুন।";
        }
      });
    }
  });

  function showToken(tok) {
    currentToken = tok;
    statusText.style.display = "none";
    tokenSection.style.display = "block";
    tokenVal.innerText = tok;
  }

  btnOpenGoogle.addEventListener("click", () => {
    chrome.tabs.create({ url: "https://accounts.google.com/EmbeddedSetup" });
  });

  btnCopy.addEventListener("click", () => {
    if (currentToken) {
      navigator.clipboard.writeText(currentToken).then(() => {
        btnCopy.innerText = "✅ কপি হয়েছে!";
        setTimeout(() => { btnCopy.innerText = "📋 টোকেন কপি করুন"; }, 2000);
      });
    }
  });

  btnOpenWeb.addEventListener("click", () => {
    if (currentToken) {
      chrome.tabs.create({ url: `${WEB_APP_URL}?token=${currentToken}` });
    } else {
      chrome.tabs.create({ url: WEB_APP_URL });
    }
  });
});
