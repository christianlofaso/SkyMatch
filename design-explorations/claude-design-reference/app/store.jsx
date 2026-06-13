/* ============================================================
   SkyMatch — shared app store (React context)
   App (app.jsx) provides the value; screens consume via useApp().
   ============================================================ */
const AppCtx = React.createContext(null);
function useApp(){ return React.useContext(AppCtx); }
window.AppCtx = AppCtx;
window.useApp = useApp;
