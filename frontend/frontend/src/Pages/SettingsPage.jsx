import { useState, useRef, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import NavigationBar from "../components/NavigationBar";
import Icons from "../components/Icons";
import "./SettingsPage.css";
import { User } from "lucide-react";

function SettingsPage() {
   const { user, authFetch, refreshUser, logout } = useAuth();
   const [activeTab, setActiveTab] = useState("profile");

   const [formData, setFormData] = useState({
      username: "",
      email: "",
      bio: "",
      avatar_base64: "",
   });

   const [previewAvatar, setPreviewAvatar] = useState(null);
   const [isSaving, setIsSaving] = useState(false);
   const [message, setMessage] = useState({ text: "", type: "" });
   const fileInputRef = useRef(null);

   useEffect(() => {
      if (user) {
         setFormData({
            username: user.username || "",
            email: user.email || "",
            bio: user.bio || "",
            avatar_base64: "", // Don't prefill base64 for existing avatar
         });
         setPreviewAvatar(user.avatar_url || null);
      }
   }, [user]);

   const handleInputChange = (e) => {
      const { name, value } = e.target;
      setFormData((prev) => ({ ...prev, [name]: value }));
   };

   const handleFileChange = (e) => {
      const file = e.target.files[0];
      if (file) {
         if (file.size > 2 * 1024 * 1024) {
            setMessage({ text: "File must be less than 2MB", type: "error" });
            return;
         }

         const reader = new FileReader();
         reader.onloadend = () => {
            setPreviewAvatar(reader.result);
            setFormData((prev) => ({ ...prev, avatar_base64: reader.result }));
         };
         reader.readAsDataURL(file);
      }
   };

   const triggerFileInput = () => {
      fileInputRef.current.click();
   };

   const handleSaveProfile = async () => {
      setIsSaving(true);
      setMessage({ text: "", type: "" });

      try {
         const response = await authFetch(
            `${import.meta.env.VITE_API_BASE_URL}/auth/profile/update/`,
            {
               method: "PATCH",
               headers: {
                  "Content-Type": "application/json",
               },
               body: JSON.stringify(formData),
            },
         );

         if (!response.ok) {
            throw new Error(`Failed to update profile: ${response.status}`);
         }

         const updatedUser = await response.json();
         // Attempt to refresh user data using the context
         await refreshUser();
         setMessage({ text: "Profile updated successfully!", type: "success" });
      } catch (error) {
         console.error("Error updating profile:", error);
         setMessage({ text: "Failed to update profile. Please try again.", type: "error" });
      } finally {
         setIsSaving(false);
      }
   };

   return (
      <div className="settings-layout">
         <NavigationBar />

         <main className="settings-container">
            <div className="settings-header">
               <h1>Settings</h1>
               <p className="settings-subtitle">
                  Manage your account preferences and extension behaviour.
               </p>
            </div>

            <div className="settings-main-wrapper">
               <div className="settings-sidebar">
                  <div className="settings-sidebar-nav">
                     <button
                        className={`settings-tab ${activeTab === "profile" ? "active" : ""}`}
                        onClick={() => setActiveTab("profile")}>
                        <Icons
                           name="user"
                           size={18}
                        />
                        Profile
                     </button>
                     <button
                        className="settings-tab"
                        disabled>
                        <Icons
                           name="lock"
                           size={18}
                        />
                        Security
                     </button>
                     <button
                        className="settings-tab"
                        disabled>
                        <Icons
                           name="bell"
                           size={18}
                        />
                        Notifications
                     </button>
                  </div>
               </div>

               <div className="settings-content">
                  {activeTab === "profile" ? (
                     <div className="settings-panel">
                        <div
                           className="panel-header"
                           style={{
                              display: "flex",
                              alignItems: "center",
                              gap: "12px",
                              marginBottom: "24px",
                              borderBottom: "1px solid var(--border-color, #e5e7eb)",
                              paddingBottom: "16px",
                           }}>
                           <div
                              style={{
                                 backgroundColor: "#4f46e5",
                                 borderRadius: "8px",
                                 padding: "6px",
                                 display: "flex",
                                 color: "white",
                              }}>
                              <Icons
                                 name="user"
                                 size={18}
                              />
                           </div>
                           <h2
                              className="panel-title"
                              style={{ margin: 0 }}>
                              Profile
                           </h2>
                        </div>

                        <div className="settings-form-group avatar-upload-row">
                           <div className="current-avatar">
                              <div
                                 className="avatar-placeholder"
                                 style={{ backgroundColor: "#e0e7ff", color: "#4f46e5" }}>
                                 {previewAvatar ? (
                                    <img
                                       src={previewAvatar}
                                       alt={`${user?.username}'s avatar`}
                                       style={{
                                          width: "100%",
                                          height: "100%",
                                          borderRadius: "50%",
                                          objectFit: "cover",
                                       }}
                                    />
                                 ) : (
                                    user?.username?.[0]?.toUpperCase() || "?"
                                 )}
                              </div>
                           </div>
                           <div className="avatar-upload-actions">
                              <input
                                 type="file"
                                 ref={fileInputRef}
                                 onChange={handleFileChange}
                                 accept="image/jpeg, image/png, image/gif"
                                 style={{ display: "none" }}
                              />
                              <button
                                 className="upload-btn"
                                 style={{
                                    color: "#4f46e5",
                                    borderColor: "#c7d2fe",
                                    backgroundColor: "#eef2ff",
                                 }}
                                 onClick={triggerFileInput}>
                                 Change Avatar
                              </button>
                              <p className="upload-hint">JPG, PNG or GIF - max 2MB</p>
                           </div>
                        </div>

                        <div className="settings-form-group">
                           <label
                              className="form-label"
                              style={{
                                 textTransform: "uppercase",
                                 fontSize: "12px",
                                 letterSpacing: "0.5px",
                              }}>
                              DISPLAY NAME
                           </label>
                           <input
                              type="text"
                              name="username"
                              value={formData.username}
                              onChange={handleInputChange}
                              className="form-input"
                              placeholder="@verifyme"
                           />
                        </div>

                        <div className="settings-form-group">
                           <label
                              className="form-label"
                              style={{
                                 textTransform: "uppercase",
                                 fontSize: "12px",
                                 letterSpacing: "0.5px",
                              }}>
                              EMAIL ADDRESS
                           </label>
                           <input
                              type="email"
                              name="email"
                              value={formData.email}
                              onChange={handleInputChange}
                              className="form-input"
                              placeholder="user@email.com"
                           />
                        </div>

                        <div className="settings-form-group">
                           <label
                              className="form-label"
                              style={{
                                 textTransform: "uppercase",
                                 fontSize: "12px",
                                 letterSpacing: "0.5px",
                              }}>
                              BIO
                           </label>
                           <input
                              type="text"
                              name="bio"
                              value={formData.bio}
                              onChange={handleInputChange}
                              className="form-input"
                              placeholder="Passionate about media literacy..."
                           />
                        </div>

                        <div
                           className="settings-actions"
                           style={{
                              marginTop: "0",
                              paddingTop: "0",
                              borderTop: "none",
                              justifyContent: "flex-start",
                              flexDirection: "column",
                              alignItems: "flex-start",
                              gap: "8px",
                           }}>
                           <button
                              className="save-btn"
                              onClick={handleSaveProfile}
                              disabled={isSaving}>
                              {isSaving ? "Saving..." : "Save Changes"}
                           </button>
                           {message.text && (
                              <div
                                 style={{
                                    color: message.type === "error" ? "#ef4444" : "#10b981",
                                    fontSize: "14px",
                                    marginTop: "8px",
                                 }}>
                                 {message.text}
                              </div>
                           )}
                        </div>
                     </div>
                  ) : (
                     <div className="settings-panel">
                        <h2 className="panel-title">Account Details</h2>
                        <p className="panel-desc">Manage your email and password.</p>

                        <div className="settings-form-group">
                           <button
                              className="settings-btn"
                              style={{ width: "100%", marginBottom: "12px" }}>
                              Change Email
                           </button>
                           <button
                              className="settings-btn"
                              style={{ width: "100%" }}>
                              Change Password
                           </button>
                        </div>
                     </div>
                  )}

                  {activeTab !== "profile" && (
                     <div className="settings-panel danger-zone">
                        <h2 className="panel-title danger-title">Danger Zone</h2>
                        <button
                           className="settings-btn danger"
                           style={{ width: "100%", marginBottom: "12px" }}>
                           Delete Account
                        </button>
                        <button
                           className="logout-btn"
                           onClick={logout}
                           style={{ width: "100%", justifyContent: "center" }}>
                           <Icons
                              name="logout"
                              size={16}
                           />
                           Log out of TruthLens
                        </button>
                     </div>
                  )}
               </div>
            </div>
         </main>
      </div>
   );
}

export default SettingsPage;
