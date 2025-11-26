import {createSignal, onMount, onCleanup} from "solid-js";
import type {
    DrivePickerElement,
    PickerPickedEvent,
} from "@googleworkspace/drive-picker-element";

declare module "solid-js" {
    namespace JSX {
        interface IntrinsicElements {
            "drive-picker": JSX.HTMLAttributes<DrivePickerElement> & {
                "client-id"?: string;
                "app-id"?: string;
                "scope"?: string;
            };

            "drive-picker-docs-view": JSX.HTMLAttributes<HTMLElement>;
        }
    }
}

export default function DrivePicker() {
    let pickerRef: DrivePickerElement | undefined;
    const [selectedFiles, setSelectedFiles] = createSignal<any[]>([]);

    onMount(async () => {
        await import("@googleworkspace/drive-picker-element");

        if (!pickerRef) return;

        if (localStorage.getItem('it')) {
            let token_info = JSON.parse(localStorage.getItem('it') as string)
            if (token_info.expires_at > Date.now()) {
                pickerRef.setAttribute('oauth-token', token_info.access_token)
            }
        }

        const handlePicked = (e: Event) => {
            const event = e as PickerPickedEvent;
            console.log("Files picked:", event.detail);
            setSelectedFiles(event.detail.docs || []);
        };

        const handleCanceled = (_e: Event) => {
            console.log("Picker canceled");
        };

        const handleOAuthError = (e: Event) => {
            console.error("OAuth error:", e);
        };
        const handleOAuthSuccess = (e: { detail: any; }) => {
            console.info("OAuth sucess:", e);
            e.detail.expires_at = Date.now() + e.detail.expires_in * 1000;
            e?.detail && localStorage.setItem('it', JSON.stringify(e.detail))
        };

        pickerRef.addEventListener("picker-picked", handlePicked);
        pickerRef.addEventListener("picker-canceled", handleCanceled);
        pickerRef.addEventListener("picker-oauth-error", handleOAuthError);
        pickerRef.addEventListener("picker-oauth-response", handleOAuthSuccess);

        onCleanup(() => {
            if (!pickerRef) return;
            pickerRef.removeEventListener("picker-picked", handlePicked);
            pickerRef.removeEventListener("picker-canceled", handleCanceled);
            pickerRef.removeEventListener("picker-oauth-error", handleOAuthError);
        });
    });

    // @ts-ignore
    return (
        <div>
            <drive-picker
                ref={el => (pickerRef = el as DrivePickerElement)}
                client-id="17520064084-tgmob015qji3cn1stsv2ener7grq27ck.apps.googleusercontent.com"
                app-id="17520064084"
                scope="https://www.googleapis.com/auth/drive.file"
            >
                <drive-picker-docs-view
                    view-id={"SPREADSHEETS"}
                ></drive-picker-docs-view>
            </drive-picker>

            {selectedFiles().length > 0 && (
                <div class={'p-4'}>
                    <ul class="list bg-base-100 rounded-box shadow-md">
                        <li class="p-4 pb-2 text-xs opacity-60 tracking-wide">Selected Files:</li>
                        {selectedFiles().map((file, index) => (
                            <li class="list-row">
                                <div class="text-4xl font-thin opacity-30 tabular-nums">{index + 1}</div>
                                <div class="justify-self-auto content-center">
                                    <div>{file.name}</div>
                                </div>
                                <button class="btn btn-square btn-ghost">
                                    <svg class="size-[1.2em]" xmlns="http://www.w3.org/2000/svg"
                                         viewBox="0 0 24 24" fill="none">
                                        <path d="M4 7H20" stroke="#000000" stroke-width="2" stroke-linecap="round"
                                              stroke-linejoin="round"/>
                                        <path
                                            d="M6 10L7.70141 19.3578C7.87432 20.3088 8.70258 21 9.66915 21H14.3308C15.2974 21 16.1257 20.3087 16.2986 19.3578L18 10"
                                            stroke="#000000" stroke-width="2" stroke-linecap="round"
                                            stroke-linejoin="round"/>
                                        <path d="M9 5C9 3.89543 9.89543 3 11 3H13C14.1046 3 15 3.89543 15 5V7H9V5Z"
                                              stroke="#000000" stroke-width="2" stroke-linecap="round"
                                              stroke-linejoin="round"/>
                                    </svg>
                                </button>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}