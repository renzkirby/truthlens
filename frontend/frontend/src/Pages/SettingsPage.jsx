import { useAuth } from "../context/AuthContext";
import NavigationBar from "../components/NavigationBar";
import Icons from "../components/Icons";
import "./SettingsPage.css";

function SettingsPage() {
   const { user, authFetch, refreshUser, logout } = useAuth();
   
   return (
      <div className="settings-layout">
         <NavigationBar />
         
         <main className="settings-container">
            <div className="settings-header">
               <h1>Settings</h1>
               <p className="settings-subtitle">Manage your account and profile preferences.</p>
            </div>

            <div className="settings-main-wrapper">
               <div className="settings-sidebar">
                  <div className="settings-sidebar-nav">
                     <button className="settings-tab active">
                        <Icons name="user" size={18} />
                        Profile Settings
                     </button>
                     <button className="settings-tab" disabled>
                        <Icons name="lock" size={18} />
                        Security 
                     </button>
                     <button className="settings-tab" disabled>
                        <Icons name="bell" size={18} />
                        Notifications 
                     </button>
                  </div>
               </div>

               <div className="settings-content">
                  <div className="settings-panel">
                     <h2 className="panel-title">Account Details</h2>
                     <p className="panel-desc">Manage your email and password.</p>

                     <div className="settings-form-group">
                        <button className="settings-btn" style={{ width: '100%', marginBottom: '12px' }}>Change Email</button>
                        <button className="settings-btn" style={{ width: '100%' }}>Change Password</button>
                     </div>
                  </div>
                  
                  <div className="settings-panel danger-zone">
                     <h2 className="panel-title danger-title">Danger Zone</h2>
                     <button className="settings-btn danger" style={{ width: '100%', marginBottom: '12px' }}>Delete Account</button>
                     <button className="logout-btn" onClick={logout} style={{ width: '100%', justifyContent: 'center' }}>
                        <Icons name="logout" size={16} />
                        Log out of TruthLens
                     </button>
                  </div>
               </div>
            </div>
         </main>
      </div>
   );
}

export default SettingsPage;
