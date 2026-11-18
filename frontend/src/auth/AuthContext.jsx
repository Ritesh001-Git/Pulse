import { createContext, useContext, useState } from "react";
import * as api from "../api/client.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("pulse_user") ?? "null");
    } catch {
      return null;
    }
  });

  const login = async (email, password) => {
    const { token, user } = await api.login(email, password);
    localStorage.setItem("pulse_token", token);
    localStorage.setItem("pulse_user", JSON.stringify(user));
    setUser(user);
    return user;
  };

  const logout = () => {
    localStorage.removeItem("pulse_token");
    localStorage.removeItem("pulse_user");
    setUser(null);
  };

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
