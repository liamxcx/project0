import { parseProfilePath } from "./routes.js";
import { renderHome } from "./sections/home.js";
import { renderProfile } from "./sections/profile.js";
import { initTooltips } from "./tooltip.js";

initTooltips();

const profile = parseProfilePath(location.pathname);

if (profile) {
  document.getElementById("home").hidden = true;
  document.getElementById("profile").hidden = false;
  renderProfile(document.getElementById("profile-content"), profile);
} else {
  renderHome(document.getElementById("followed"));
}
