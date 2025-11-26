import {useLocation} from "@solidjs/router";
import { A } from "@solidjs/router";

export default function Nav() {
    const location = useLocation();

    return (
        <div class="navbar bg-base-100 shadow-sm">
            <div class="flex-1">
                <a class="btn btn-ghost text-xl">Vocab AI</a>
            </div>
            <div class="flex-none">

                <div class="dropdown dropdown-end">
                    <A href={'/'} tabIndex="0" role="button" class="btn btn-ghost btn-circle avatar">
                        <div class="w-10 rounded-full">
                            <img
                                alt="Profile"
                                src="https://img.daisyui.com/images/stock/photo-1534528741775-53994a69daeb.webp"/>
                        </div>
                    </A>
                    <ul
                        tabIndex="-1"
                        class="menu menu-sm dropdown-content bg-base-100 rounded-box z-1 mt-3 w-52 p-2 shadow">
                        <li>
                            <a class="justify-between">
                                Profile
                            </a>
                        </li>
                        <li><A href={'/settings'}>Settings</A></li>
                        <li><A href={'/'}>Logout</A></li>
                    </ul>
                </div>
            </div>
        </div>
    );
}
