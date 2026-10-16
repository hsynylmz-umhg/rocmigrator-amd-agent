import Image from "next/image";
import Link from "next/link";

interface NavbarProps {
  readonly currentState?: string | null;
  readonly isBusy?: boolean;
  readonly connection?: string;
}

export function Navbar({ currentState, isBusy, connection }: NavbarProps = {}) {
  const isReconnecting = connection === "reconnecting";

  let statusText = "Ready to migrate";
  let dotColor = "bg-emerald-400";
  let dotPing = "bg-emerald-400";
  let pillBorder = "border-emerald-500/30";
  let pillBg = "bg-emerald-500/10";
  let textColor = "text-emerald-300";

  if (isBusy || (currentState && !["ROLLED_BACK", "PR_CREATED", "USER_APPROVAL"].includes(currentState))) {
    statusText = currentState ? `Running: ${currentState}` : "Migration in progress";
    dotColor = "bg-rose-500";
    dotPing = "bg-rose-500";
    pillBorder = "border-rose-500/40";
    pillBg = "bg-rose-500/15";
    textColor = "text-rose-300";
  } else if (currentState === "USER_APPROVAL") {
    statusText = "Awaiting approval";
    dotColor = "bg-amber-400";
    dotPing = "bg-amber-400";
    pillBorder = "border-amber-400/40";
    pillBg = "bg-amber-400/15";
    textColor = "text-amber-200";
  } else if (currentState === "ROLLED_BACK") {
    statusText = "Rolled back";
    dotColor = "bg-rose-500";
    dotPing = "bg-rose-500";
    pillBorder = "border-rose-500/40";
    pillBg = "bg-rose-500/15";
    textColor = "text-rose-300";
  } else if (currentState === "PR_CREATED") {
    statusText = "Pull request ready";
    dotColor = "bg-emerald-400";
    dotPing = "bg-emerald-400";
    pillBorder = "border-emerald-500/30";
    pillBg = "bg-emerald-500/10";
    textColor = "text-emerald-300";
  } else if (isReconnecting) {
    statusText = "Reconnecting…";
    dotColor = "bg-amber-400";
    dotPing = "bg-amber-400";
    pillBorder = "border-amber-400/40";
    pillBg = "bg-amber-400/15";
    textColor = "text-amber-200";
  }

  return (
    <header className="border-b border-[#3d191e] bg-[#180b0d]/90 backdrop-blur-sm">
      <div className="mx-auto flex max-w-[1520px] flex-wrap items-center justify-between gap-4 px-4 py-3 sm:px-8 lg:px-10">
        <div className="flex items-center gap-5">
          <Link
            href="/"
            aria-label="ROCmigrator home"
            className="flex shrink-0 items-center gap-3 rounded-sm transition-transform duration-200 hover:scale-[1.02]"
          >
            <Image
              src="/logo.png"
              alt=""
              width={48}
              height={48}
              priority
              className="h-11 w-11 object-contain drop-shadow-[0_0_10px_rgba(225,29,72,0.35)]"
            />
            <span className="text-xl font-bold tracking-tight text-foreground">ROCmigrator</span>
          </Link>
          <span className="hidden border-l border-[#3d191e] pl-5 text-sm text-brand-khaki md:inline">
            Migration workspace
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div
            className={`flex items-center gap-2 rounded-full border ${pillBorder} ${pillBg} px-3 py-1.5 text-xs font-medium ${textColor} shadow-sm transition-all duration-200`}
          >
            <span className="relative flex h-2 w-2">
              <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${dotPing} opacity-75`} />
              <span className={`relative inline-flex h-2 w-2 rounded-full ${dotColor}`} />
            </span>
            <span>{statusText}</span>
          </div>

          <span className="flex items-center gap-2.5 rounded-lg border border-[#3d191e] bg-[#231013] px-3 py-1.5 font-mono text-xs text-brand-khaki shadow-sm">
            CUDA
            <span
              aria-hidden="true"
              className="flex h-5 w-5 items-center justify-center rounded bg-rose-900 text-xs font-semibold text-foreground shadow-sm"
            >
              →
            </span>
            <span className="sr-only">to</span>
            HIP / ROCm
          </span>
        </div>
      </div>
    </header>
  );
}
