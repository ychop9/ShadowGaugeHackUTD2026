// Wraps the login page so it fades in smoothly after the vault door opens.
// The dark background stops a white flash while the page fades in.
export default function LoginTemplate({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#12041f]">
      <div className="animate-[page-enter_700ms_cubic-bezier(0.22,1,0.36,1)_both]">{children}</div>
    </div>
  );
}
