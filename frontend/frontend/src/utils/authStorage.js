export const getAccessToken = () => localStorage.getItem("access") || sessionStorage.getItem("access");

export const getRefreshToken = () => localStorage.getItem("refresh") || sessionStorage.getItem("refresh");

export const getAuthStorage = () => (localStorage.getItem("access") ? localStorage : sessionStorage);

export const storeAuthTokens = (access, refresh, rememberMe = false) => {
   clearAuthTokens();

   const storage = rememberMe ? localStorage : sessionStorage;

   if (access) {
      storage.setItem("access", access);
   }

   if (refresh) {
      storage.setItem("refresh", refresh);
   }
};

export const updateAuthTokens = (access, refresh) => {
   const storage = getAuthStorage();

   if (access) {
      storage.setItem("access", access);
   }

   if (refresh) {
      storage.setItem("refresh", refresh);
   }
};

export const clearAuthTokens = () => {
   localStorage.removeItem("access");
   localStorage.removeItem("refresh");

   sessionStorage.removeItem("access");
   sessionStorage.removeItem("refresh");
};
