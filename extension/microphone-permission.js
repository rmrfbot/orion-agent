const requestButton = document.querySelector("#request-microphone");
const permissionStatus = document.querySelector("#permission-status");

requestButton.addEventListener("click", async () => {
  requestButton.disabled = true;
  permissionStatus.textContent = "Waiting for Chrome's microphone prompt...";

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((track) => track.stop());
    permissionStatus.textContent = "Microphone access granted. Close this tab and click Start listening in Orion's side panel.";
  } catch (error) {
    permissionStatus.textContent = `Chrome could not grant access (${error.name}). Check chrome://settings/content/microphone and macOS Microphone privacy settings.`;
    requestButton.disabled = false;
  }
});