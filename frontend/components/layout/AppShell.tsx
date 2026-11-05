"use client";
import { BrandMark } from "@/components/ui/geometry";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import {
  LayoutDashboard,
  BriefcaseBusiness,
  Bookmark,
  CheckCheck,
  Bell,
  SlidersHorizontal,
  Building2,
  Settings,
  Menu,
  X,
  PanelLeftClose,
  Search,
  ChevronDown,
} from "lucide-react";
import Logout from "@/components/Logout";
import { Button } from "@/components/ui/primitives";
import { ToastProvider } from "@/components/ui/feedback";
const routes = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/jobs", label: "Jobs", icon: BriefcaseBusiness },
  { href: "/saved", label: "Saved", icon: Bookmark },
  { href: "/applied", label: "Applied", icon: CheckCheck },
  { href: "/notifications", label: "Notifications", icon: Bell },
  { href: "/profiles", label: "Profiles", icon: SlidersHorizontal },
  { href: "/companies", label: "Companies", icon: Building2 },
  { href: "/account", label: "Account", icon: Settings },
];
export default function AppShell({
  email,
  unread,
  children,
}: {
  email: string;
  unread: number;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const [mobile, setMobile] = useState(false),
    [collapsed, setCollapsed] = useState(false);
  const navigation = (
    <nav aria-label="Main navigation">
      {routes.map(({ href, label, icon: Icon }) => (
        <Link
          prefetch={false}
          key={href}
          href={href}
          title={collapsed ? label : undefined}
          aria-current={
            pathname === href || pathname.startsWith(href + "/")
              ? "page"
              : undefined
          }
          onClick={() => setMobile(false)}
        >
          <Icon size={19} aria-hidden="true" />
          <span>{label}</span>
          {href === "/notifications" && unread > 0 && (
            <small aria-label={`${unread} unread notifications`}>
              {unread > 99 ? "99+" : unread}
            </small>
          )}
        </Link>
      ))}
    </nav>
  );
  return (
    <ToastProvider>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
        <aside className="sidebar">
          <Link prefetch={false} href="/dashboard" className="brand">
            <BrandMark />
            <span>
              JobPulse<span className="brand-dot">.</span>
            </span>
          </Link>
          <p className="nav-caption">YOUR WORKSPACE</p>
          {navigation}
          <div className="sidebar-bottom">
            <p>
              Official careers.
              <br />
              Relevant opportunities.
            </p>
            <Button
              variant="ghost"
              onClick={() => setCollapsed(!collapsed)}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              aria-expanded={!collapsed}
            >
              <PanelLeftClose size={18} />
            </Button>
          </div>
        </aside>
        <div className="shell-body">
          <header className="app-header">
            <Dialog.Root open={mobile} onOpenChange={setMobile}>
              <Dialog.Trigger asChild>
                <Button
                  className="mobile-menu"
                  variant="ghost"
                  aria-label="Open navigation"
                >
                  <Menu size={21} />
                </Button>
              </Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="dialog-overlay" />
                <Dialog.Content className="mobile-sidebar">
                  <Dialog.Title className="brand">
                    <BrandMark />
                    JobPulse
                  </Dialog.Title>
                  <Dialog.Description className="sr-only">
                    Navigate your workspace
                  </Dialog.Description>
                  <Dialog.Close asChild>
                    <Button
                      className="sheet-close"
                      aria-label="Close navigation"
                    >
                      <X size={18} />
                    </Button>
                  </Dialog.Close>
                  {navigation}
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
            <form action="/jobs" className="header-search">
              <Search size={17} aria-hidden="true" />
              <input
                name="search"
                aria-label="Search jobs"
                placeholder="Search your opportunities…"
              />
            </form>
            <div className="header-right">
              <Link
                prefetch={false}
                href="/notifications"
                className="notification-link"
                aria-label={`Notifications, ${unread} unread`}
              >
                <Bell size={20} />
                {unread > 0 && <span className="notification-dot" />}
              </Link>
              <Dropdown.Root>
                <Dropdown.Trigger asChild>
                  <Button variant="ghost" className="user-trigger">
                    <span className="avatar">
                      {email.slice(0, 1).toUpperCase()}
                    </span>
                    <span className="user-email">{email}</span>
                    <ChevronDown size={14} />
                  </Button>
                </Dropdown.Trigger>
                <Dropdown.Portal>
                  <Dropdown.Content
                    className="dropdown"
                    align="end"
                    sideOffset={8}
                  >
                    <Dropdown.Label className="dropdown-label">
                      Signed in as
                      <br />
                      <strong>{email}</strong>
                    </Dropdown.Label>
                    <Dropdown.Item asChild>
                      <Link prefetch={false} href="/account">
                        Account
                      </Link>
                    </Dropdown.Item>
                    <Dropdown.Separator />
                    <Logout menu />
                  </Dropdown.Content>
                </Dropdown.Portal>
              </Dropdown.Root>
            </div>
          </header>
          <main id="main-content" className="app-content">
            {children}
          </main>
          <footer className="app-footer">
            Your search, in focus.<span>JobPulse</span>
          </footer>
        </div>
      </div>
    </ToastProvider>
  );
}
