"use client";

import { useEffect, useState } from "react";
import { Bell, Moon, Search, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CommandPalette } from "./CommandPalette";

export function Header() {
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur">
        <div className="flex h-16 items-center gap-3 px-4 sm:px-6 lg:px-8">
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            aria-label="Open global search"
            className="flex h-10 min-w-0 flex-1 items-center gap-3 rounded-lg border border-border bg-card/80 px-3 text-sm text-muted-foreground transition hover:border-border/80 hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            <Search className="size-4 shrink-0 text-muted-foreground" />
            <span className="truncate">Search targets, incidents, containers</span>
            <span className="ml-auto hidden rounded-md border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground sm:inline">
              Ctrl K
            </span>
          </button>

          <div className="hidden items-center gap-2 rounded-full border border-border bg-card/80 px-3 py-1.5 text-xs text-emerald-300 md:flex">
            <span className="size-2 rounded-full bg-emerald-400" />
            API online
          </div>
          <Button variant="outline" size="icon" className="border-border bg-card/80" aria-label="Notifications">
            <Bell className="size-4" />
          </Button>
          <Button variant="outline" size="icon" className="border-border bg-card/80" aria-label="Theme">
            <Moon className="size-4" />
          </Button>
          <Button variant="outline" size="icon" className="border-border bg-card/80" aria-label="User menu">
            <User className="size-4" />
          </Button>
        </div>
      </header>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </>
  );
}
