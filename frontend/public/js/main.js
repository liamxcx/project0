import { parseProfilePath } from "./routes.js";
import { renderHome } from "./sections/home.js";
import { renderProfile } from "./sections/profile.js";
import { renderRefreshButton } from "./sections/refresh-button.js";
import { initTooltips } from "./tooltip.js";

initTooltips();

const profile = parseProfilePath(location.pathname);

if (profile) {
  document.getElementById("home").hidden = true;
  document.getElementById("profile").hidden = false;
  const content = document.getElementById("profile-content");
  renderProfile(content, profile);
  // Cuando acaba el collector se vuelve a pintar el perfil, que pide los datos de nuevo
  renderRefreshButton(document.getElementById("refresh"), () => renderProfile(content, profile));
} else {
  renderHome(document.getElementById("followed"));
}
