import { parseProfilePath } from "./routes.js";
import { renderHome } from "./sections/home.js";
import { renderProfile } from "./sections/profile.js";

const profile = parseProfilePath(location.pathname);

if (profile) {
  document.getElementById("home").hidden = true;
  renderProfile(document.getElementById("profile"), profile);
} else {
  renderHome(document.getElementById("followed"));
}
