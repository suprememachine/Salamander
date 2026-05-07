// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title BaseMineToken (BASEMINE)
 * @dev ERC-20 mining reward token for Base Mining platform
 *      Minted by mining rewards, traded via AMM on Base L2
 */
contract BaseMineToken {
    string public constant name = "Base Mine Token";
    string public constant symbol = "BMINE";
    uint8 public constant decimals = 18;
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    address public owner;
    address public minter;  // mining reward contract / backend
    bool public mintingEnabled = true;
    uint256 public maxSupply = 1_000_000_000 * 1e18; // 1B max

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event MinterChanged(address indexed oldMinter, address indexed newMinter);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier onlyMinter() {
        require(msg.sender == minter || msg.sender == owner, "Not authorized");
        _;
    }

    constructor() {
        owner = msg.sender;
        minter = msg.sender;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "Insufficient balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        emit Transfer(msg.sender, to, amount);
        return true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(balanceOf[from] >= amount, "Insufficient balance");
        require(allowance[from][msg.sender] >= amount, "Insufficient allowance");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
        return true;
    }

    /**
     * @dev Mint new tokens (mining reward). Called by minter or owner.
     *      Subject to max supply cap.
     */
    function mint(address to, uint256 amount) external onlyMinter {
        require(mintingEnabled, "Minting disabled");
        require(totalSupply + amount <= maxSupply, "Exceeds max supply");
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    function setMinter(address _minter) external onlyOwner {
        require(_minter != address(0), "Zero address");
        emit MinterChanged(minter, _minter);
        minter = _minter;
    }

    function setMintingEnabled(bool enabled) external onlyOwner {
        mintingEnabled = enabled;
    }

    function setMaxSupply(uint256 _max) external onlyOwner {
        require(_max >= totalSupply, "Below current supply");
        maxSupply = _max;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Zero address");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }
}
